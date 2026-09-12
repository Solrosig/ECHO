"""Gradio/ZeroGPU entry point; also runs on an ordinary CPU/GPU server."""
import os,sys,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parent
archive=ROOT/'backend.zip'
if archive.is_file():
    target=ROOT/'backend';target.mkdir(exist_ok=True)
    with zipfile.ZipFile(archive) as z:
        for name in z.namelist():
            if not (target/name).resolve().is_relative_to(target.resolve()):raise RuntimeError('Unsafe source archive member.')
        z.extractall(target)
    sys.path[:0]=[str(target),str(target/'vendor'),str(target/'vendor/Matcha-TTS')]
else:sys.path[:0]=[str(ROOT),str(ROOT/'vendor'),str(ROOT/'vendor/Matcha-TTS')]
import torch
import gradio as gr
import spaces
import models
import nltk
nltk.download('punkt_tab',quiet=True)

torch.set_num_threads(2)
# Pinned checkpoints are unpickled freely only while models.load_engine runs (models.trusted_checkpoint_loads).

# The website's server voices: TEST_ENGINES and EXPLORE_ENGINES in engine-catalog.js, less the in-browser Kokoro.
# ZipVoice is not offered on the website, so the Space loads it only when ECHO_ENGINES names it.
SITE_ENGINES=['chatterbox','styletts2','cosyvoice2','parlertts']
enabled=os.environ.get('ECHO_ENGINES',','.join(SITE_ENGINES)).split(',')
failures={}
for engine in enabled:
    try:models.load_engine(engine)
    except Exception as exc:
        failures[engine]=str(exc);print(f'Could not initialise {engine}: {exc}',flush=True)

@spaces.GPU(duration=60)
def gpu_synthesize(text,engine,emotion,condition):
    return models.render(text,engine,emotion,condition)

def synthesize(text,engine,emotion,condition):
    if engine not in enabled:raise gr.Error('This engine is not enabled.')
    if engine in failures:raise gr.Error(f'{engine} could not initialise: {failures[engine]}')
    try:return gpu_synthesize(text,engine,emotion,condition)
    except Exception as exc:
        import traceback
        traceback.print_exc()
        raise gr.Error(f'{type(exc).__name__}: {exc}') from exc

with gr.Blocks(delete_cache=(300,300)) as demo:
    gr.Markdown('# ECHO speech service\nSynthetic speech for an academic study of user-selected emotion. Generated files are temporary; listener ratings are stored by the ECHO website separately.')
    if failures:gr.Markdown('**Unavailable engines:** '+', '.join(failures));gr.JSON(failures,label='Initialisation diagnostics')
    text=gr.Textbox(label='Text',max_lines=5)
    engine=gr.Dropdown(enabled,value=next((e for e in enabled if e not in failures),enabled[0]),label='TTS engine')
    emotion=gr.Dropdown(['happy','upset','sad','calm'],value='calm',label='Emotion chosen by you')
    condition=gr.Dropdown(['preset','neutral'],value='preset',label='Condition')
    button=gr.Button('Generate speech')
    speech=gr.Audio(label='Synthetic speech',type='filepath')
    metadata=gr.JSON(label='Generation metadata')
    button.click(synthesize,[text,engine,emotion,condition],[speech,metadata],api_name='synthesize',concurrency_limit=1)
# Full ECHO website and durable private data beside the existing TTS API.
from fastapi import FastAPI
import uvicorn
from web_host import prepare,add_web_routes,DURABLE,LOCAL
store,web_process,public_origin=prepare()
demo.queue(max_size=12)
app=gr.mount_gradio_app(FastAPI(docs_url=None,redoc_url=None,openapi_url=None),demo,path='/api/tts',blocked_paths=[str(DURABLE),str(LOCAL)],show_error=True,ssr_mode=False,server_port=7860)
app=add_web_routes(app,store,public_origin)
server=uvicorn.Server(uvicorn.Config(app,host='0.0.0.0',port=int(os.environ.get('ECHO_HTTP_PORT','7860'))))
demo.server=server
# Mounting on FastAPI bypasses Blocks.launch and its ZeroGPU startup hook.
# Invoke the same installed Spaces hook after model loading, before serving.
from spaces.config import Config as SpacesConfig
if SpacesConfig.zero_gpu:
    from spaces.zero import startup as zerogpu_startup
    zerogpu_startup()
server.run()
