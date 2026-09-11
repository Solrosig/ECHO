import {collectSpeechResult} from './speech-events.js';
import {Client} from '@gradio/client';
import {calibratedAudio} from './prosody.js';
import {SPEECH_SERVICE} from './speech-service-config.js';
export class RemoteSpeechClient{
 constructor(){this.job=null;this.cancelled=false;}
 reset(){this.cancelled=true;void this.job?.cancel();this.job=null;}
 async run(data,onEvent=()=>{}){
  this.cancelled=false;let timer,context,app;
  try{
   onEvent({type:'progress',text:'Connecting to the speech service…'});
   app=await Promise.race([Client.connect(SPEECH_SERVICE,{events:['data','status']}),new Promise((_,reject)=>{timer=setTimeout(()=>reject(new Error('The speech service is starting or unavailable. Wait and retry.')),60000);})]);clearTimeout(timer);
   if(this.cancelled)throw new Error('Generation cancelled.');
   const job=app.submit('/synthesize',{text:data.text,engine:data.params.engine,emotion:data.params.emotion,condition:data.params.condition});this.job=job;
   let response;
   const consume=async()=>{response=await collectSpeechResult(job,event=>{onEvent({type:'progress',text:event.stage==='pending'?`Waiting for the speech service${Number.isFinite(event.position)?' · queue position '+(event.position+1):''}…`:`Generating with ${data.params.engine}…`});},()=>this.cancelled);};
   await Promise.race([consume(),new Promise((_,reject)=>{timer=setTimeout(()=>{void job.cancel();reject(new Error('Speech generation timed out. Try a shorter line.'));},180000);})]);clearTimeout(timer);
   if(!response?.[0]?.url)throw new Error('The speech service did not return an audio file.');
   const meta=response[1];if(!meta||meta.engine!==data.params.engine||meta.condition!==data.params.condition)throw new Error('The speech result does not match the requested engine or condition.');
   const url=new URL(response[0].url,app.config?.root||SPEECH_SERVICE),base=new URL(SPEECH_SERVICE,location.origin);if(url.origin!==base.origin)throw new Error('Unexpected speech-file host.');
   const audio=await fetch(url);if(!audio.ok)throw new Error('The generated audio expired. Please generate it again.');const wav=await audio.arrayBuffer();if(this.cancelled)throw new Error('Generation cancelled.');
   context=new AudioContext();const decoded=await context.decodeAudioData(wav);if(decoded.numberOfChannels!==1)throw new Error('The speech service must return mono audio.');
   return {...response[1],...calibratedAudio(decoded.getChannelData(0),decoded.sampleRate,data.params),service_metadata:response[1],conditioning:data.params.conditioning};
  }finally{clearTimeout(timer);app?.close();if(context)await context.close();this.job=null;}
 }
}
