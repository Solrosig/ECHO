"""Pinned ECHO adapters. Native model outputs; final calibrated DSP runs in the site."""
from pathlib import Path
import os, json, random, tempfile
from contextlib import contextmanager
import numpy as np
import soundfile as sf
import torch
from huggingface_hub import snapshot_download, hf_hub_download

os.environ['ECHO_TEXT_FRONTEND']='0'  # Text is passed unchanged to the model tokenizer.
torch.set_num_threads(2)
ROOT=Path(__file__).resolve().parent
REFERENCES=ROOT/'refs'
DEVICE='cuda' if os.environ.get('SPACE_ID') or torch.cuda.is_available() else 'cpu'
LOCK=json.loads((ROOT/'models.lock.json').read_text())
ENGINES=['chatterbox','styletts2','cosyvoice2','parlertts','zipvoice']
INSTRUCTIONS={'happy':'Speak in a happy, upbeat and energetic tone.','upset':'Speak in an angry, agitated and tense tone.','sad':'Speak in a sad, subdued and downhearted tone.','calm':'Speak in a calm, warm and relaxed tone.'}
REFS={'happy':'Q1','upset':'Q2','sad':'Q3','calm':'Q4'}
MODELS={}

def snapshot(engine,patterns=None):
    info=LOCK[engine]
    local=os.environ.get('ECHO_MODEL_'+engine.upper())
    return local or snapshot_download(info['repo'],revision=info['revision'],allow_patterns=patterns)

@contextmanager
def trusted_checkpoint_loads():
    """Let the upstream loaders read the pinned checkpoints, which carry metadata beyond tensors.

    torch>=2.6 defaults to weights_only=True. The override lasts only while an engine loads from its pinned
    revision, no user-supplied weights or paths are accepted, and torch.load is restored afterwards.
    """
    original=torch.load
    def load(*args,**kwargs):
        kwargs.setdefault('weights_only',False)
        return original(*args,**kwargs)
    torch.load=load
    try:yield
    finally:torch.load=original

def load_engine(engine):
    if engine in MODELS:return MODELS[engine]
    with trusted_checkpoint_loads():return _load_engine(engine)

def _load_engine(engine):
    if engine=='chatterbox':
        from chatterbox.tts import ChatterboxTTS
        directory=snapshot(engine,['ve.safetensors','t3_cfg.safetensors','s3gen.safetensors','tokenizer.json','conds.pt'])
        model=ChatterboxTTS.from_local(directory,device=DEVICE)
    elif engine=='styletts2':
        from styletts2 import tts
        info=LOCK[engine]; source=LOCK['styletts2_source']
        tts.LIBRI_TTS_CHECKPOINT_URL=f"https://huggingface.co/{info['repo']}/resolve/{info['revision']}/Models/LibriTTS/epochs_2nd_00020.pth"
        tts.LIBRI_TTS_CONFIG_URL=f"https://huggingface.co/{info['repo']}/resolve/{info['revision']}/Models/LibriTTS/config.yml"
        for key in ['ASR_CHECKPOINT_URL','ASR_CONFIG_URL','F0_CHECKPOINT_URL','BERT_CHECKPOINT_URL','BERT_CONFIG_URL']:
            setattr(tts,key,getattr(tts,key).replace('/raw/main/',f"/raw/{source['revision']}/"))
        model=tts.StyleTTS2();model.device=DEVICE
        for part in model.model.values():part.to(DEVICE)
    elif engine=='cosyvoice2':
        from cosyvoice.cli.cosyvoice import CosyVoice2
        directory=snapshot(engine,['CosyVoice-BlankEN/*','*.yaml','*.json','llm.pt','flow.pt','hift.pt','speech_tokenizer_v2.onnx','campplus.onnx','spk2info.pt'])
        model=CosyVoice2(directory,load_jit=False,load_trt=False,fp16=False)
    elif engine=='parlertts':
        from parler_tts import ParlerTTSForConditionalGeneration
        from transformers import AutoTokenizer
        directory=snapshot(engine)
        model=(ParlerTTSForConditionalGeneration.from_pretrained(directory,attn_implementation='eager').to(DEVICE),AutoTokenizer.from_pretrained(directory))
    elif engine=='zipvoice':
        from zipvoice.bin.infer_zipvoice import ZipVoice,EmiliaTokenizer,VocosFbank,get_vocoder
        import safetensors.torch
        directory=Path(snapshot(engine,['zipvoice/model.safetensors','zipvoice/model.json','zipvoice/tokens.txt']))/'zipvoice'
        tokenizer=EmiliaTokenizer(token_file=str(directory/'tokens.txt'))
        config=json.loads((directory/'model.json').read_text())
        core=ZipVoice(**config['model'],vocab_size=tokenizer.vocab_size,pad_id=tokenizer.pad_id)
        safetensors.torch.load_model(core,str(directory/'model.safetensors'))
        vocoder_dir=snapshot('vocos',['config.yaml','pytorch_model.bin'])
        model=(core.to(DEVICE).eval(),get_vocoder(vocoder_dir).to(DEVICE).eval(),tokenizer,VocosFbank())
    else:raise ValueError('Unknown engine')
    MODELS[engine]=model
    return model

def render(text,engine,emotion,condition='preset',output=None):
    if not isinstance(text,str) or not text.strip() or len(text)>800:raise ValueError('Enter 1–800 characters.')
    if engine not in ENGINES or emotion not in REFS or condition not in ['preset','neutral']:raise ValueError('Invalid synthesis selection.')
    torch.manual_seed(666);np.random.seed(666);random.seed(666)
    model=load_engine(engine)
    reference=REFERENCES/('neutral.wav' if condition=='neutral' or engine=='cosyvoice2' else REFS[emotion]+'.wav')
    instruction='Speak in a neutral tone.' if condition=='neutral' else INSTRUCTIONS[emotion]
    arousal=0 if condition=='neutral' else (.6 if emotion in ['happy','upset'] else -.6)
    if output is None:
        fd,output=tempfile.mkstemp(prefix='echo-',suffix='.wav');os.close(fd)
    with torch.inference_mode():
        if engine=='chatterbox':
            audio=model.generate(text,audio_prompt_path=str(reference),exaggeration=.3+.55*(arousal+1)/2,cfg_weight=.6-.3*(arousal+1)/2)
            sf.write(output,audio.squeeze().detach().cpu().numpy(),model.sr,subtype='PCM_16')
        elif engine=='styletts2':
            model.inference(text,target_voice_path=str(reference),output_wav_file=output,alpha=.3,beta=.7,diffusion_steps=5)
        elif engine=='cosyvoice2':
            from cosyvoice.utils.file_utils import load_wav
            # ZeroGPU has no real CUDA stream during module initialisation.
            if DEVICE=='cuda':model.model.llm_context=torch.cuda.stream(torch.cuda.Stream(torch.device(DEVICE)))
            prompt=load_wav(str(reference),16000)
            chunks=[x['tts_speech'] for x in model.inference_instruct2(text,instruction,prompt,stream=False,text_frontend=False)]
            if not chunks:raise ValueError('CosyVoice2 returned no speech.')
            sf.write(output,torch.cat(chunks,dim=1).squeeze().cpu().numpy(),model.sample_rate,subtype='PCM_16')
        elif engine=='parlertts':
            core,tokenizer=model
            desc=tokenizer(instruction+' Jon is speaking. The recording is very clear audio, close up.',return_tensors='pt').to(DEVICE)
            prompt=tokenizer(text,return_tensors='pt').to(DEVICE)
            audio=core.generate(input_ids=desc.input_ids,attention_mask=desc.attention_mask,prompt_input_ids=prompt.input_ids,prompt_attention_mask=prompt.attention_mask)
            sf.write(output,audio.squeeze().cpu().numpy(),core.config.sampling_rate,subtype='PCM_16')
        elif engine=='zipvoice':
            from zipvoice.bin.infer_zipvoice import generate_sentence
            core,vocoder,tokenizer,features=model
            generate_sentence(save_path=output,prompt_text='Kids are talking by the door.',prompt_wav=str(reference),text=text,model=core,vocoder=vocoder,tokenizer=tokenizer,feature_extractor=features,device=torch.device(DEVICE),num_step=16,guidance_scale=1.0,speed=1.0,target_rms=.1)
    audio,sr=sf.read(output)
    if audio.ndim!=1 or len(audio)/sr<.4 or len(audio)/sr>600 or not np.isfinite(audio).all() or np.max(np.abs(audio))<1e-4:raise ValueError('Generated audio failed the signal validation.')
    return str(output),{'engine':engine,'model':LOCK[engine]['repo'],'revision':LOCK[engine]['revision'],'runtime':'ECHO native adapters v1','duration_s':len(audio)/sr,'seed':666,'reference':reference.name,'instruction':instruction,'condition':condition}

if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--jobs',required=True);args=parser.parse_args()
    for job in json.loads(Path(args.jobs).read_text()):
        output,meta=render(job['text'],job['engine'],job['emotion'],job.get('condition','preset'),job['output'])
        Path(output+'.json').write_text(json.dumps(meta,indent=2));print(output,flush=True)
