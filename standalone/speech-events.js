// Gradio can emit completion while its async iterator remains open.
export async function collectSpeechResult(job,onStatus=()=>{},isCancelled=()=>false){
 let data;const iterator=job[Symbol.asyncIterator]();
 // No for-await: leaving one calls return(), which in this client version waits on an empty queue.
 for(;;){
  const {value:event,done}=await iterator.next();if(done)return data;
  if(isCancelled())throw new Error('Generation cancelled.');
  if(event.type==='data')data=event.data;
  if(event.type==='status'){
   if(event.stage==='error')throw new Error(event.message||'Speech generation failed.');
   onStatus(event);
   if(event.stage==='complete')return data;
  }
 }
 return data;
}

