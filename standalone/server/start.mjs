import {createServer} from 'node:http';
import {createReadStream,existsSync,statSync,realpathSync,mkdirSync} from 'node:fs';
import {resolve,join,extname,sep} from 'node:path';
import {fileURLToPath} from 'node:url';
import {Readable} from 'node:stream';
import worker from './worker.js';
import {localAudio} from './local-audio.js';
import {localDatabase} from './local-db.js';
import {createAuth} from './auth.mjs';
import {QWEN_REVISION} from './llm-backup.mjs';
import {dialogueConfig,createMetricsLog} from './dialogue.mjs';
import {proxySpeech} from './speech-proxy.mjs';
import {SHOW_RESEARCH_PAGE} from '../frontend-visibility.js';
const ROOT=fileURLToPath(new URL('../',import.meta.url));
const MIME={'.html':'text/html;charset=utf-8','.js':'text/javascript;charset=utf-8','.mjs':'text/javascript;charset=utf-8','.css':'text/css;charset=utf-8','.json':'application/json','.txt':'text/plain;charset=utf-8','.svg':'image/svg+xml','.png':'image/png','.ico':'image/x-icon','.wav':'audio/wav','.wasm':'application/wasm','.zip':'application/zip','.gz':'application/gzip'};
const json=(value,status=200,headers={})=>new Response(JSON.stringify(value),{status,headers:{'Content-Type':'application/json','Cache-Control':'no-store',...headers}});
export function createEchoServer({dataDir=resolve(ROOT,'data'),clientDir=resolve(ROOT,'dist/client'),publicDir=resolve(ROOT,'public'),publicOrigin=null,host='127.0.0.1',allowLocalContainer=false,speechService=process.env.ECHO_TTS_URL||'http://127.0.0.1:7860',dialogue=dialogueConfig()}={}) {
  if(publicOrigin){const u=new URL(publicOrigin);if(u.origin!==publicOrigin||u.protocol!=='https:')throw new Error('PUBLIC_ORIGIN must be an HTTPS origin without a trailing slash.');}
  if(host!=='127.0.0.1'&&host!=='::1'&&!publicOrigin&&!allowLocalContainer)throw new Error('A non-loopback server requires PUBLIC_ORIGIN=https://your-domain.');
  if(!existsSync(join(clientDir,'index.html')))throw new Error('Built website missing: restore dist/client from the archive or run pnpm build.');
  clientDir=realpathSync(clientDir);const assetDirs=[clientDir,realpathSync(publicDir)];mkdirSync(dataDir,{recursive:true,mode:0o700});
  const auth=createAuth(dataDir,{secure:Boolean(publicOrigin)}),DB=localDatabase(join(dataDir,'study.sqlite')),dialogueLog=createMetricsLog(join(dataDir,'dialogue-metrics.jsonl'));
  function staticFile(req,res,url){
    if(!['GET','HEAD'].includes(req.method)){res.writeHead(405);return res.end();}
    let path;try{path=decodeURIComponent(url.pathname);}catch{res.writeHead(400);return res.end();}
    if(!SHOW_RESEARCH_PAGE && /^\/research(?:\.html)?\/?$/.test(path)){
      res.writeHead(302,{'Location':'/','Cache-Control':'no-store'});return res.end();
    }
    const aliases={'/':'/index.html','/studio':'/studio.html','/listen':'/listen.html','/research':'/research.html','/calibration/':'/calibration/index.html','/calibration':'/calibration/index.html'};path=aliases[path]||path;
    // WebLLM expects a resolve/revision URL layout even for a local model host.
    const qwenPrefix=`/models/qwen/resolve/${QWEN_REVISION}/`;
    if(path.startsWith(qwenPrefix))path='/models/qwen/'+path.slice(qwenPrefix.length);
    if(path.includes('\0')||path.includes('\\')||path.split('/').some(x=>x.startsWith('.'))){res.writeHead(404);return res.end();}
    let file,stat;
    for(const dir of assetDirs){try{const candidate=realpathSync(resolve(dir,'.'+path));if(!candidate.startsWith(dir+sep))continue;const info=statSync(candidate);if(!info.isFile())continue;file=candidate;stat=info;break;}catch{}}
    if(!file){res.writeHead(404);return res.end('Not found');}
    const headers={'Content-Type':MIME[extname(file)]||'application/octet-stream','Accept-Ranges':'bytes','Content-Length':stat.size,'Cache-Control':path.startsWith('/assets/')?'public,max-age=31536000,immutable':path.startsWith('/models/')?'public,max-age=86400':'no-cache'};
    let start=0,end=stat.size-1,status=200;
    if(req.headers.range){const m=req.headers.range.match(/^bytes=(\d*)-(\d*)$/);if(!m||!m[1]&&!m[2]){res.writeHead(416,{'Content-Range':`bytes */${stat.size}`});return res.end();}
      if(!m[1])start=Math.max(0,stat.size-Number(m[2]));else {start=Number(m[1]);if(m[2])end=Math.min(end,Number(m[2]));}
      if(!Number.isSafeInteger(start)||start>end||start<0){res.writeHead(416,{'Content-Range':`bytes */${stat.size}`});return res.end();}
      status=206;headers['Content-Range']=`bytes ${start}-${end}/${stat.size}`;headers['Content-Length']=end-start+1;
    }
    res.writeHead(status,headers);if(req.method==='HEAD'||stat.size===0)return res.end();
    const stream=createReadStream(file,{start,end});stream.on('error',()=>res.destroy());stream.pipe(res);res.on('close',()=>stream.destroy());
  }
  const server=createServer({maxHeaderSize:16384,requestTimeout:30000,headersTimeout:15000},async(req,res)=>{
    res.setHeader('X-Content-Type-Options','nosniff');res.setHeader('Referrer-Policy','no-referrer');res.setHeader('X-Frame-Options','DENY');
    // Every model, WASM module and application resource is served by this host.
    res.setHeader('Content-Security-Policy',"default-src 'self'; script-src 'self' 'wasm-unsafe-eval'; worker-src 'self' blob:; connect-src 'self' blob:; style-src 'self' 'unsafe-inline'; img-src 'self' data:; media-src 'self' blob:; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'");
    try{
      const port=server.address()?.port;
      const allowed=publicOrigin?[new URL(publicOrigin).host]:[`127.0.0.1:${port}`,`localhost:${port}`,`[::1]:${port}`];
      // Reverse-proxy deployments preserve the configured public Host; forwarded identity is ignored.
      if(!allowed.includes(req.headers.host)){res.writeHead(421);return res.end('Use the configured website address.');}
      const origin=publicOrigin||`http://${req.headers.host}`,url=new URL(req.url,origin);
      if(url.origin!==origin){res.writeHead(400);return res.end();}
      if(url.pathname==='/api/tts'||url.pathname.startsWith('/api/tts/'))return await proxySpeech(req,res,url,origin,speechService);
      if(!url.pathname.startsWith('/api/'))return staticFile(req,res,url);
      const request=new Request(url,{method:req.method,headers:req.headers,body:['GET','HEAD'].includes(req.method)?undefined:Readable.toWeb(req),duplex:'half'});
      let response;
      if(url.pathname.startsWith('/api/auth/')){
        if(req.method!=='POST')response=json({error:'Method not allowed.'},405);
        else if(request.headers.get('origin')!==origin||request.headers.get('sec-fetch-site')==='cross-site')response=json({error:'Only this website can sign in.'},403);
        else if(url.pathname==='/api/auth/logout')response=json({ok:true},200,{'Set-Cookie':auth.logout(request)});
        else if(url.pathname==='/api/auth/login'){
          if(!request.headers.get('content-type')?.startsWith('application/json'))response=json({error:'Send JSON.'},415);
          else{let content='',bytes=0;for await(const chunk of request.body){bytes+=chunk.byteLength;if(bytes>2048)break;content+=new TextDecoder().decode(chunk);}
            if(bytes>2048)response=json({error:'Request too large.'},413);
            else{let data;try{data=JSON.parse(content);}catch{data={};}
              const result=auth.login(data.password,req.socket.remoteAddress);
              response=json(result.status===200?{ok:true}:{error:result.error},result.status,result.cookie?{'Set-Cookie':result.cookie}:{});
            }
          }
        }else response=json({error:'Not found.'},404);
      }else response=await worker.fetch(request,{DB,AUDIO:localAudio(join(dataDir,'audio')),RESEARCHER_AUTHORIZED:auth.authorised(request),DIALOGUE:{config:dialogue,log:dialogueLog}},{});
      res.writeHead(response.status,Object.fromEntries(response.headers));res.end(Buffer.from(await response.arrayBuffer()));
    }catch(error){console.error('Request failed:',error.message);if(!res.headersSent)res.writeHead(500,{'Content-Type':'application/json','Cache-Control':'no-store'});res.end(JSON.stringify({error:'The server could not complete this request.'}));}
  });
  server.on('close',()=>DB.close());return server;
}
if(process.argv[1]&&resolve(process.argv[1])===fileURLToPath(import.meta.url)){
  try{
    const major=Number(process.versions.node.split('.')[0]);if(major!==24)throw new Error('This release requires Node.js 24 LTS.');
    const host=process.env.HOST||'127.0.0.1',port=Number(process.env.PORT||8787),publicOrigin=process.env.PUBLIC_ORIGIN||null;
    if(!Number.isInteger(port)||port<1||port>65535)throw new Error('Invalid PORT.');
    const server=createEchoServer({host,publicOrigin,dataDir:resolve(process.env.ECHO_DATA_DIR||join(ROOT,'data')),allowLocalContainer:process.env.ECHO_ALLOW_LOCAL_CONTAINER==='1'});
    server.on('error',e=>{console.error(e.code==='EADDRINUSE'?'Port is busy. Set a different PORT and retry.':e.message);process.exitCode=1;});
    server.listen(port,host,()=>console.log(`ECHO ready: ${publicOrigin||`http://${host}:${port}`}\nResearch dashboard: /research\nStop with Ctrl+C. Data remain on disk.`));
    for(const signal of ['SIGINT','SIGTERM'])process.once(signal,()=>{server.close(()=>process.exit(0));server.closeIdleConnections();setTimeout(()=>process.exit(1),10000).unref();});
  }catch(error){console.error(error.message);process.exitCode=1;}
}
