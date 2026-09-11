// Conversation replies come from the ECHO server, which asks the local language model. The page never names a model.
export async function requestReply({text,emotion,history=[]},{signal,fetchImpl=fetch}={}){
  const response=await fetchImpl('/api/dialogue/reply',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text,emotion,history}),signal});
  let data={};try{data=await response.json();}catch{}
  if(!response.ok||typeof data?.text!=='string')throw new Error(data?.error||'The conversation reply could not be generated. Try again.');
  return data;
}
