import {calibratedAudio} from './prosody.js';
import {KokoroTTS} from 'kokoro-js';
import {env} from '@huggingface/transformers';
import {audioResult} from './audio-utils.js';
import {speechChunks} from './voice-controls.js';
import {seconds} from './generation-timing.js';
import {KOKORO_REVISION} from './model-config.js';
env.allowLocalModels=true;
env.allowRemoteModels=false;
env.localModelPath=new URL('/models/',self.location.origin).href;
env.backends.onnx.wasm.numThreads=1;
env.backends.onnx.wasm.wasmPaths=new URL('/vendor/kokoro-ort/',self.location.origin).href;
// kokoro-js 1.2.1 has a fixed upstream voice URL. Resolve its one selected voice locally.
const originalFetch=self.fetch.bind(self);
self.fetch=(input,init)=>{
  const url=typeof input==='string'?input:input instanceof URL?input.href:input.url;
  if(url==='https://huggingface.co/onnx-community/Kokoro-82M-v1.0-ONNX/resolve/main/voices/af_heart.bin')
    return originalFetch(new URL('/models/kokoro/voices/af_heart.bin',self.location.origin),init);
  return originalFetch(input,init);
};
let tts,busy=false;
self.onmessage=async({data})=>{
  const send=(event,transfer=[])=>self.postMessage({...event,id:data.id},transfer);
  const progress=text=>send({type:'progress',text});
  if(busy)return send({type:'error',message:'A model operation is already active.'});busy=true;
  try{
    if(data.task==='speech'){
      const began=performance.now(),cold=!tts;
      if(!tts){
        progress('Loading the bundled Kokoro voice model…');
        tts=await KokoroTTS.from_pretrained('kokoro',{dtype:'q8',device:'wasm',progress_callback:p=>{if(p.status==='progress')progress(`Loading Kokoro · ${Math.round(p.progress||0)}% · ${p.file||''}`);}});
      }
      const loaded=performance.now();
      progress('Synthesising with Kokoro. This may take a minute on this device…');
      const parts=speechChunks(data.text),chunks=[];let sampleRate;
      for(const [i,text] of parts.entries()){progress(`Synthesising with Kokoro · part ${i+1} of ${parts.length}…`);const audio=await tts.generate(text,{voice:data.params.voice,speed:data.params.rate});chunks.push(audio.audio);sampleRate=audio.sampling_rate;}
      const synthesised=performance.now();
      const pcm=new Float32Array(chunks.reduce((n,c)=>n+c.length,0));let offset=0;for(const c of chunks){pcm.set(c,offset);offset+=c.length;}
      const result={...calibratedAudio(pcm,sampleRate,data.params),text_segments:parts.length,model:'onnx-community/Kokoro-82M-v1.0-ONNX',model_revision:KOKORO_REVISION,runtime:'kokoro-js-1.2.1/q8/wasm'};
      // The model loads once per worker (a cold start); synthesis and ECHO's level and pitch processing run on this device.
      result.timing={engine_location:'browser',cold_start:cold,model_load_s:cold?seconds(loaded-began):null,synthesis_s:seconds(synthesised-loaded),browser_processing_s:seconds(performance.now()-synthesised),text_segments:parts.length};
      send({type:'result',result},[result.buffer]);
    }else throw new Error('Unknown model task.');
  }catch(e){send({type:'error',message:e.message||String(e)});}finally{busy=false;}
};
