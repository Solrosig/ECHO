"""Serve the standalone ECHO application beside its existing Gradio TTS service."""
import asyncio,hashlib,json,os,secrets,shutil,subprocess,tarfile,threading,time,urllib.request,zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import httpx
from fastapi import FastAPI,Request
from starlette.responses import Response,StreamingResponse
from persistent_store import Store,sha,write_closed

ROOT=Path(__file__).resolve().parent
WEB=ROOT/'webapp'
LOCAL=Path(os.environ.get('ECHO_LOCAL_DATA','/tmp/echo-web-data'))
DURABLE=Path(os.environ.get('ECHO_PERSISTENT_DIR','/data/echo'))
NODE_VERSION='v24.21.0'
NODE_SHA='fd8e59d5a511510f6a298afb548f18c7d2b1be404d8b4a27d94fbe49f56cb2d6'
OLLAMA_VERSION='v0.30.11'
OLLAMA_SHA='11dc89b6c68f136f85ef10e00957530ffab61c35f227696dbf8a11169b47f165'
OLLAMA_MODEL='llama3.2:3b'
# The llama3.2:3b build (Q4_K_M) the 2026-09-11 prompt screen used; any other build is refused.
OLLAMA_MODEL_DIGEST='a80c4f17acd55265feec403c7aef86be0c25983ab279d83f3bcd3abbcb5b8b72'
OLLAMA_PROCESS=None

def unpack(archive,dest):
    dest=Path(dest);dest.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(archive) as z:
        for name in z.namelist():
            if not (dest/name).resolve().is_relative_to(dest.resolve()):raise RuntimeError('Invalid archive path')
        z.extractall(dest)

def researcher_credentials(directory,password):
    """Store only a salted scrypt hash of the researcher password, in the format server/auth.mjs verifies."""
    if not isinstance(password,str) or not 16<=len(password)<=256:
        raise RuntimeError('Before the first launch, set the Space secret ECHO_ADMIN_PASSWORD (16-256 characters). ECHO stores only its salted hash.')
    salt=secrets.token_bytes(32)
    digest=hashlib.scrypt(password.encode(),salt=salt.hex().encode(),n=16384,r=8,p=1,dklen=64)
    write_closed(Path(directory)/'researcher.json',json.dumps({'version':1,'salt':salt.hex(),'hash':digest.hex()}).encode())

def llm_mode():
    """ECHO_LLM_MODE: off (no conversation replies), embedded (Ollama inside this Space, on paid GPU hardware)
    or remote (a private Ollama Space at ECHO_OLLAMA_URL, called with the secret ECHO_OLLAMA_TOKEN)."""
    mode=os.environ.get('ECHO_LLM_MODE','off').strip().lower()
    if mode not in ('off','embedded','remote'):raise RuntimeError('ECHO_LLM_MODE must be off, embedded or remote.')
    return mode

def model_digest(tags,name=OLLAMA_MODEL):
    return next((m.get('digest') for m in tags.get('models',[]) if m.get('name')==name),None)

def cpu_limit(root='/sys/fs/cgroup'):
    """Whole CPUs the container's cgroup quota allows (cgroup v2, then v1), or None when there is no quota."""
    root=Path(root)
    try:
        quota,period=(root/'cpu.max').read_text().split()[:2]
        return None if quota=='max' else max(1,int(quota)//int(period))
    except (OSError,ValueError):pass
    try:
        quota,period=int((root/'cpu/cpu.cfs_quota_us').read_text()),int((root/'cpu/cpu.cfs_period_us').read_text())
        return max(1,quota//period) if quota>0 and period>0 else None
    except (OSError,ValueError):return None

def ollama_threads(env=os.environ,root='/sys/fs/cgroup',cores=None):
    """Threads for the conversation model. Unless told, llama-server starts one per physical core of the host (96 on the
    ZeroGPU host of 2026-09-12), and under the container's CPU quota that many threads can stall it. ECHO_OLLAMA_THREADS
    sets the count; otherwise it follows the quota, and None leaves llama.cpp's own count where there is no quota."""
    chosen=str(env.get('ECHO_OLLAMA_THREADS','')).strip()
    if chosen:
        if not chosen.isdigit() or int(chosen)<1:raise RuntimeError('ECHO_OLLAMA_THREADS must be a whole number of at least 1.')
        return int(chosen)
    limit=cpu_limit(root)
    if cores is None:cores=len(os.sched_getaffinity(0)) if hasattr(os,'sched_getaffinity') else os.cpu_count() or 1
    return min(limit,cores) if limit else None

def ollama_environment(cache,threads):
    cache=Path(cache)
    # The voices are loaded first. Ollama sizes itself to the GPU memory left, so it is told to keep a margin (default
    # 2 GiB) for the voices' working memory during synthesis; on a small GPU it moves some model layers to the CPU instead.
    env={**os.environ,'OLLAMA_HOST':'127.0.0.1:11434','OLLAMA_MODELS':str(cache/'models'),'OLLAMA_KEEP_ALIVE':'-1','HOME':str(cache/'home'),
         'OLLAMA_GPU_OVERHEAD':os.environ.get('ECHO_OLLAMA_GPU_OVERHEAD',str(2*1024**3))}
    # Ollama passes -t only for a model's num_thread option, which would reload the model whenever a request differs, so the
    # count travels in the environment llama-server inherits from Ollama (LLAMA_ARG_THREADS is its --threads).
    if threads:env['LLAMA_ARG_THREADS']=str(threads)
    return env

def start_embedded_ollama(cache):
    """Run the pinned Ollama and model inside this Space. They download to local disk again after every wake-up."""
    global OLLAMA_PROCESS
    cache=Path(cache);runtime=cache/'runtime';binary=runtime/'bin/ollama';base='http://127.0.0.1:11434';threads=ollama_threads()
    print(f"Starting Ollama on {os.environ.get('ACCELERATOR','unknown hardware')}; without a GPU it runs on the CPU. "
          f"Container CPU limit: {cpu_limit() or 'none'}; model threads: {threads or 'llama.cpp default'}.",flush=True)
    if not binary.exists():
        runtime.mkdir(parents=True,exist_ok=True);archive=cache/'ollama-linux-amd64.tar.zst'
        urllib.request.urlretrieve(f'https://github.com/ollama/ollama/releases/download/{OLLAMA_VERSION}/ollama-linux-amd64.tar.zst',archive)
        if sha(archive)!=OLLAMA_SHA:archive.unlink();raise RuntimeError('Ollama runtime checksum mismatch')
        subprocess.run(['tar','--zstd','-xf',str(archive),'-C',str(runtime)],check=True);archive.unlink()
    (cache/'home').mkdir(parents=True,exist_ok=True)
    # The voices are loaded first. Ollama sizes itself to the GPU memory left, so it is told to keep a margin (default
    # 2 GiB) for the voices' working memory during synthesis; on a small GPU it moves some model layers to the CPU instead.
    env={**os.environ,'OLLAMA_HOST':'127.0.0.1:11434','OLLAMA_MODELS':str(cache/'models'),'OLLAMA_KEEP_ALIVE':'-1','HOME':str(cache/'home'),
         'OLLAMA_GPU_OVERHEAD':os.environ.get('ECHO_OLLAMA_GPU_OVERHEAD',str(2*1024**3))}
    OLLAMA_PROCESS=subprocess.Popen([str(binary),'serve'],env=env)
    for _ in range(240):
        if OLLAMA_PROCESS.poll() is not None:raise RuntimeError('Ollama stopped during startup')
        try:
            if httpx.get(base+'/api/version',timeout=2).status_code==200:break
        except httpx.HTTPError:pass
        time.sleep(.5)
    else:raise RuntimeError('Ollama did not start')
    if model_digest(httpx.get(base+'/api/tags',timeout=10).json())!=OLLAMA_MODEL_DIGEST:
        httpx.post(base+'/api/pull',json={'model':OLLAMA_MODEL,'stream':False},timeout=httpx.Timeout(3600,connect=10)).raise_for_status()
    digest=model_digest(httpx.get(base+'/api/tags',timeout=10).json())
    if digest!=OLLAMA_MODEL_DIGEST:
        OLLAMA_PROCESS.terminate();raise RuntimeError(f'{OLLAMA_MODEL} is build {digest}, not the tested {OLLAMA_MODEL_DIGEST[:12]}')
    httpx.post(base+'/api/generate',json={'model':OLLAMA_MODEL,'keep_alive':-1},timeout=httpx.Timeout(600,connect=10)).raise_for_status()
    print(f'Conversation model ready: {OLLAMA_MODEL} build {OLLAMA_MODEL_DIGEST[:12]}.',flush=True)

def run_embedded_ollama():
    try:start_embedded_ollama(os.environ.get('ECHO_OLLAMA_CACHE','/tmp/echo-ollama'))
    except Exception as exc:print(f'Conversation replies unavailable: {exc}',flush=True)

def prepare():
    mode=llm_mode()
    if not WEB.exists():unpack(ROOT/'webapp.zip',WEB)
    # Preserve Window as the receiver of native fetch in Chromium. The bundled
    # standalone sync classes previously called fetch as their own method.
    # Patch both editable sources and prebuilt assets; no experiment settings change.
    targets=list((WEB/'dist/client').rglob('*.js'))+[WEB/'study-sync.js',WEB/'interactive-sync.js']
    for target in targets:
        if target.is_file():
            content=target.read_text()
            patched=content.replace('this.fetcher(', 'this.fetcher.call(globalThis,')
            if patched!=content:target.write_text(patched)
    for target in (WEB/'dist/client').rglob('*.html'):
        content=target.read_text()
        patched=content.replace('all 30 final ratings','all 45 final ratings')
        patched=patched.replace('Speech and conversation generation run on your device.', 'Kokoro and conversation text generation run on your device; other neural voices use the ECHO speech service.')
        # The historical auxiliary calibration gallery is not part of this release.
        import re
        patched=re.sub(r'<a[^>]+href="/calibration/"[^>]*>.*?</a>', '', patched)
        if patched!=content:target.write_text(patched)
    # Version the complete asset graph so browsers cannot reuse immutable
    # pre-fix JavaScript from an earlier visit to this same domain.
    assets=WEB/'dist/client/assets'
    rename={p.name:p.stem+'-hf2.js' for p in assets.glob('*.js') if not p.stem.endswith('-hf2')}
    if rename:
        for target in list((WEB/'dist/client').rglob('*.js'))+list((WEB/'dist/client').rglob('*.html')):
            content=target.read_text()
            for old,new in rename.items():content=content.replace(old,new)
            target.write_text(content)
        for old,new in rename.items():(assets/old).rename(assets/new)
    # /data must be an explicitly mounted bucket in the Space. A bare ephemeral
    # directory must never be presented as persistent research storage.
    if os.environ.get('SPACE_ID') and not os.path.ismount('/data'):
        if not any(' /data ' in line for line in Path('/proc/mounts').read_text().splitlines()):raise RuntimeError('Mount the private research bucket at /data before launching ECHO')
    LOCAL.mkdir(parents=True,exist_ok=True);DURABLE.mkdir(parents=True,exist_ok=True)
    credentials=DURABLE/'researcher.json'
    if not credentials.exists():researcher_credentials(DURABLE,os.environ.get('ECHO_ADMIN_PASSWORD',''))
    if (DURABLE/'RESEARCHER_ACCESS.txt').exists():print('RESEARCHER_ACCESS.txt in the research bucket holds a plaintext researcher password from an earlier version. Delete it from the bucket; researcher.json keeps only the salted hash.',flush=True)
    shutil.copyfile(credentials,LOCAL/'researcher.json')
    store=Store(LOCAL,DURABLE)
    if not (LOCAL/'study.sqlite').exists():store.restore()
    store.restore_metrics()
    node=os.environ.get('ECHO_NODE') or shutil.which('node')
    if not node or not subprocess.check_output([node,'--version'],text=True).startswith('v24.'):
        cache=Path('/tmp/echo-node');cache.mkdir(exist_ok=True)
        node=str(cache/f'node-{NODE_VERSION}-linux-x64/bin/node')
        if not Path(node).exists():
            archive=cache/'node.tar.xz';urllib.request.urlretrieve(f'https://nodejs.org/dist/{NODE_VERSION}/node-{NODE_VERSION}-linux-x64.tar.xz',archive)
            if sha(archive)!=NODE_SHA:raise RuntimeError('Node runtime checksum mismatch')
            with tarfile.open(archive) as t:
                for item in t.getmembers():
                    if not (cache/item.name).resolve().is_relative_to(cache.resolve()):raise RuntimeError('Invalid Node archive')
                t.extractall(cache)
    def download(row):
        target=WEB/row['path'];target.parent.mkdir(parents=True,exist_ok=True)
        if target.exists() and sha(target)==row['sha256']:return
        for attempt in range(3):
            try:
                tmp=target.with_suffix(target.suffix+'.download')
                with urllib.request.urlopen(row['url'],timeout=120) as r,open(tmp,'wb') as out:shutil.copyfileobj(r,out)
                if sha(tmp)!=row['sha256']:raise RuntimeError('Model checksum mismatch: '+target.name)
                tmp.replace(target);return
            except Exception:
                if attempt==2:raise
                time.sleep(1+attempt)
    rows=json.loads((WEB/'downloads.json').read_text())
    print('Loading pinned browser models for ECHO...',flush=True)
    with ThreadPoolExecutor(max_workers=4) as pool:list(pool.map(download,rows))
    origin=os.environ.get('ECHO_PUBLIC_ORIGIN','https://'+os.environ.get('SPACE_HOST','your-space.hf.space'))
    # The Space runs Ollama itself (embedded) or reaches a remote one, so the website never launches it.
    env={**os.environ,'HOST':'127.0.0.1','PORT':'8787','PUBLIC_ORIGIN':origin,'ECHO_DATA_DIR':str(LOCAL),'ECHO_TRUST_PROXY':'1','ECHO_OLLAMA_AUTOSTART':'0'}
    if mode=='remote':
        if not (os.environ.get('ECHO_OLLAMA_URL') and os.environ.get('ECHO_OLLAMA_TOKEN')):print('ECHO_LLM_MODE=remote needs the variable ECHO_OLLAMA_URL and the secret ECHO_OLLAMA_TOKEN; conversation replies stay unavailable.',flush=True)
    else:
        env['ECHO_OLLAMA_URL']='http://127.0.0.1:11434';env.pop('ECHO_OLLAMA_TOKEN',None)
        if mode=='off':print('Conversation replies are off (ECHO_LLM_MODE=off); Listening and Test work normally.',flush=True)
    child=subprocess.Popen([node,str(WEB/'server/start.mjs')],env=env)
    for _ in range(120):
        if child.poll() is not None:raise RuntimeError('Web process stopped during startup')
        try:
            r=httpx.get('http://127.0.0.1:8787/api/study/status',headers={'host':origin.split('//',1)[1]},timeout=2)
            if r.status_code==200:break
        except httpx.HTTPError:pass
        time.sleep(.25)
    else:raise RuntimeError('Web process did not become ready')
    if store.last is None:store.checkpoint()
    # The website serves Listening at once; the conversation model starts beside it and Explore waits for it.
    if mode=='embedded':threading.Thread(target=run_embedded_ollama,daemon=True,name='echo-ollama').start()
    return store,child,origin

def add_web_routes(app,store,origin):
    lock=asyncio.Lock()
    async def proxy(request:Request):
        path=request.url.path
        if path=='/health':return Response(json.dumps({'app':'ECHO','storage':'private-bucket-snapshots','ready':True}),media_type='application/json')
        # Only the Node server's explicit public directories and API are exposed.
        # No static mount of ROOT, /tmp or /data is created here.
        headers={k:v for k,v in request.headers.items() if k.lower() not in ['host','connection','transfer-encoding','content-length','accept-encoding']}
        headers['host']=origin.split('//',1)[1]
        headers['accept-encoding']='identity'
        body=bytearray()
        async for chunk in request.stream():
            body.extend(chunk)
            if len(body)>16*1024*1024:return Response('Request too large',status_code=413)
        url='http://127.0.0.1:8787'+path+('?' + request.url.query if request.url.query else '')
        async def forward():
            client=httpx.AsyncClient(timeout=httpx.Timeout(120,connect=10))
            try:
                response=await client.send(client.build_request(request.method,url,headers=headers,content=bytes(body)),stream=True)
                h={k:v for k,v in response.headers.items() if k not in ['connection','transfer-encoding','content-length','x-frame-options']}
                if 'content-security-policy' in h:h['content-security-policy']=h['content-security-policy'].replace("frame-ancestors 'none'","frame-ancestors 'self' https://huggingface.co")
                if path.startswith('/api/'):
                    data=await response.aread();await response.aclose();await client.aclose()
                    if request.method in ['POST','PUT','PATCH','DELETE'] and not path.startswith('/api/auth/') and response.status_code<400:
                        await asyncio.to_thread(store.checkpoint)
                    elif path=='/api/dialogue/reply':
                        # A failed reply saves no study data, but its latency and error belong in the reply metrics.
                        try:await asyncio.to_thread(store.checkpoint_metrics)
                        except Exception as error:print('Could not keep conversation-reply metrics:',error,flush=True)
                    return Response(data,status_code=response.status_code,headers=h)
                async def stream():
                    try:
                        async for chunk in response.aiter_raw():yield chunk
                    finally:await response.aclose();await client.aclose()
                return StreamingResponse(stream(),status_code=response.status_code,headers=h)
            except Exception:
                await client.aclose()
                return Response(json.dumps({'error':'The response could not be saved or served. Please retry.'}),status_code=503,media_type='application/json')
        if path.startswith('/api/'):
            async with lock:return await forward()
        return await forward()
    app.add_api_route('/{path:path}',proxy,methods=['GET','HEAD','POST','PUT','PATCH','DELETE'],include_in_schema=False)
    return app
