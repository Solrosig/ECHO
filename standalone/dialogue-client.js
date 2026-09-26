// Conversation replies come from the ECHO server, which asks its language model. The page never names a model.
// link ({session_id, turn_order, attempt_id}) lets the server's metrics line join the saved message; it never changes the reply.
export async function requestReply({text,emotion,history=[],link},{signal,fetchImpl=fetch}={}){
  const response=await fetchImpl('/api/dialogue/reply',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text,emotion,history,...link}),signal});
  let data={};try{data=await response.json();}catch{}
  if(!response.ok||typeof data?.text!=='string'){
    const error=new Error(data?.error||'The conversation reply could not be generated. Try again.');
    error.waking=data?.waking===true;error.retryAfterS=Number(data?.retry_after_s)||15;
    throw error;
  }
  return data;
}

// Asks whether the conversation model is ready; on a hosted copy this also wakes a sleeping model.
export async function checkDialogue({fetchImpl=fetch}={}){
  try{const response=await fetchImpl('/api/dialogue/status',{cache:'no-store'});return await response.json();}
  catch{return {ready:false,waking:false};}
}

const pause=(ms,signal)=>new Promise((resolve,reject)=>{
  if(signal?.aborted)return reject(signal.reason);
  const timer=setTimeout(resolve,ms);signal?.addEventListener('abort',()=>{clearTimeout(timer);reject(signal.reason);},{once:true});
});

// While a hosted model wakes up, keep asking for up to maxWaitMs; any other failure is reported at once.
export async function requestReplyWhenReady(input,{signal,fetchImpl=fetch,onWaiting=()=>{},maxWaitMs=240000,now=Date.now,sleep=pause}={}){
  const started=now();
  for(;;){
    try{return await requestReply(input,{signal,fetchImpl});}
    catch(error){
      if(!error.waking||now()-started+error.retryAfterS*1000>maxWaitMs)throw error;
      onWaiting(Math.round((now()-started)/1000));
      await sleep(error.retryAfterS*1000,signal);
    }
  }
}
