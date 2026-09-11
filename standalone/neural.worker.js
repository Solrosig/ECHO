import {calibratedAudio} from './prosody.js';
import {KokoroTTS} from 'kokoro-js';
import {env} from '@huggingface/transformers';
import {MLCEngine} from '@mlc-ai/web-llm';
import {audioResult} from './audio-utils.js';
import {speechChunks} from './voice-controls.js';
import {KOKORO_REVISION,QWEN_REVISION} from './model-config.js';
const MODEL='Qwen2.5-1.5B-Instruct-q4f32_1-MLC';
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
let tts,llm,busy=false;
self.onmessage=async({data})=>{
  const send=(event,transfer=[])=>self.postMessage({...event,id:data.id},transfer);
  const progress=text=>send({type:'progress',text});
  if(busy)return send({type:'error',message:'A model operation is already active.'});busy=true;
  try{
    if(data.task==='speech'){
      if(!tts){
        progress('Loading the bundled Kokoro voice model…');
        tts=await KokoroTTS.from_pretrained('kokoro',{dtype:'q8',device:'wasm',progress_callback:p=>{if(p.status==='progress')progress(`Loading Kokoro · ${Math.round(p.progress||0)}% · ${p.file||''}`);}});
      }
      progress('Synthesising with Kokoro. This may take a minute on this device…');
      const parts=speechChunks(data.text),chunks=[];let sampleRate;
      for(const [i,text] of parts.entries()){progress(`Synthesising with Kokoro · part ${i+1} of ${parts.length}…`);const audio=await tts.generate(text,{voice:data.params.voice,speed:data.params.rate});chunks.push(audio.audio);sampleRate=audio.sampling_rate;}
      const pcm=new Float32Array(chunks.reduce((n,c)=>n+c.length,0));let offset=0;for(const c of chunks){pcm.set(c,offset);offset+=c.length;}
      const result={...calibratedAudio(pcm,sampleRate,data.params),text_segments:parts.length,model:'onnx-community/Kokoro-82M-v1.0-ONNX',model_revision:KOKORO_REVISION,runtime:'kokoro-js-1.2.1/q8/wasm'};
      send({type:'result',result},[result.buffer]);
    }else if(data.task==='dialogue'){
      if(!self.navigator.gpu)throw new Error('Conversation replies require desktop Chrome/Edge with WebGPU. Test mode works without a language model.');
      if(!llm){
        for(const [attempt,cacheBackend] of ['cache','cache','indexeddb'].entries()){
          llm=new MLCEngine({initProgressCallback:p=>progress(p.text),appConfig:{cacheBackend,model_list:[{model:new URL(`/models/qwen/resolve/${QWEN_REVISION}/`,self.location.origin).href,model_id:MODEL,model_lib:new URL('/models/qwen/model.wasm',self.location.origin).href,low_resource_required:true,overrides:{context_window_size:2048}}]}});
          try{await llm.reload(MODEL,{context_window_size:2048});break;}
          catch(e){await llm.unload().catch(()=>{});llm=null;if(attempt===2||!/fetch|cache|network/i.test(e.message))throw e;progress(`Retrying bundled language-model loading (${attempt+2}/3)…`);}
        }
      }
      progress('Writing a reply with your chosen emotion…');await llm.resetChat();
      const stream=await llm.chat.completions.create({messages:data.messages,temperature:.7,seed:666,max_tokens:150,stream:true});
      let text='',finish;
      for await(const c of stream){const choice=c.choices?.[0];if(choice?.delta?.content){text+=choice.delta.content;send({type:'text',text});}if(choice?.finish_reason)finish=choice.finish_reason;}
      if(!text.trim()||finish==='length')throw new Error('The reply was empty or incomplete. Try a shorter message.');
      send({type:'result',result:{text:text.trim(),model:MODEL,emotion_source:'user',messages:data.messages,seed:666,temperature:.7,max_tokens:150}});
    }else throw new Error('Unknown model task.');
  }catch(e){send({type:'error',message:e.message||String(e)});}finally{busy=false;}
};
