import {appendFileSync} from 'node:fs';
import {dialogueMessages,DIALOGUE_PROMPT_VERSION,unwrapQuotedReply} from './dialogue-prompt.mjs';
import {QWEN_BACKUP_ALLOWED,QWEN_BACKUP_MODEL} from './llm-backup.mjs';

// ECHO's primary language model is llama3.2:3b served by local Ollama (decision 2026-09-11).
export const PRIMARY_MODEL='llama3.2:3b';
// The generation settings the 1.5.0 conversation used, kept so replies stay comparable.
export const GENERATION={temperature:.7,seed:666,max_tokens:150};

export class DialogueError extends Error{constructor(status,message){super(message);this.status=status;}}

// ECHO_COHERENCE_GATE: 'off' = option B, the reply comes straight from Ollama (in use since 2026-09-11).
//                      'on'  = option A, the same request goes through ECHO's coherence gate (gate_service.py).
export function dialogueConfig(env=process.env){
  const gate=String(env.ECHO_COHERENCE_GATE||'off').trim().toLowerCase();
  if(!['off','on'].includes(gate))throw new Error('ECHO_COHERENCE_GATE must be off or on.');
  const model=env.ECHO_LLM_BACKUP==='1'?QWEN_BACKUP_MODEL:(env.ECHO_OLLAMA_MODEL||PRIMARY_MODEL);
  if(/qwen/i.test(model)&&!QWEN_BACKUP_ALLOWED)throw new Error('The backup language model is locked in this version; unset ECHO_LLM_BACKUP and ECHO_OLLAMA_MODEL.');
  const timeoutMs=Number(env.ECHO_LLM_TIMEOUT_MS||120000);
  if(!Number.isFinite(timeoutMs)||timeoutMs<1000)throw new Error('ECHO_LLM_TIMEOUT_MS must be at least 1000.');
  return {
    gate,model,timeoutMs,
    ollamaUrl:String(env.ECHO_OLLAMA_URL||'http://127.0.0.1:11434').replace(/\/+$/,''),
    gateUrl:String(env.ECHO_GATE_URL||'http://127.0.0.1:8790').replace(/\/+$/,''),
  };
}

async function postJson(fetchImpl,url,payload,timeoutMs){
  const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),timeoutMs);
  try{
    const response=await fetchImpl(url,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload),signal:controller.signal});
    let data=null;try{data=await response.json();}catch{}
    return {response,data};
  }catch{
    throw new DialogueError(503,'The local language model is not reachable. Start Ollama and try again.');
  }finally{clearTimeout(timer);}
}

// Error messages never name a model: they reach the page.
export async function dialogueReply(input,config,{fetchImpl=fetch}={}){
  if(!config)throw new DialogueError(503,'Conversation replies are not configured on this server.');
  let messages;
  try{messages=dialogueMessages(input?.text,input?.emotion,Array.isArray(input?.history)?input.history:[]);}
  catch(error){throw new DialogueError(400,error.message);}
  if(config.gate==='on'){
    const {response,data}=await postJson(fetchImpl,`${config.gateUrl}/v1/gated-reply`,{messages,emotion:input.emotion,model:config.model,...GENERATION},config.timeoutMs);
    const text=typeof data?.text==='string'?unwrapQuotedReply(data.text):'';
    if(!response.ok||!text)throw new DialogueError(502,'The coherence gate could not produce a reply. Try again.');
    return {text,gate:'on',prompt_version:DIALOGUE_PROMPT_VERSION,passed:data.passed===true,attempts:Array.isArray(data.attempts)?data.attempts.length:0};
  }
  const {response,data}=await postJson(fetchImpl,`${config.ollamaUrl}/v1/chat/completions`,{model:config.model,messages,...GENERATION,stream:false},config.timeoutMs);
  if(response.status===404)throw new DialogueError(503,'The language model is not installed in Ollama.');
  if(!response.ok)throw new DialogueError(502,'The language model could not produce a reply. Try again.');
  const choice=data?.choices?.[0],text=typeof choice?.message?.content==='string'?unwrapQuotedReply(choice.message.content):'';
  if(!text||choice.finish_reason==='length')throw new DialogueError(502,'The reply was empty or incomplete. Try a shorter message.');
  return {text,gate:'off',prompt_version:DIALOGUE_PROMPT_VERSION};
}

// One JSON line per reply in the private data folder, so option B's latency and failures can be reviewed.
export function createMetricsLog(file){
  return entry=>{try{appendFileSync(file,JSON.stringify(entry)+'\n',{mode:0o600});}catch(error){console.error('Could not record dialogue metrics:',error.message);}};
}

export async function handleDialogueRequest(request,env,{readBody,json}){
  const started=Date.now(),dialogue=env.DIALOGUE;let input={};
  const record=fields=>dialogue?.log?.({utc:new Date().toISOString(),gate:dialogue?.config?.gate,model:dialogue?.config?.model,prompt_version:DIALOGUE_PROMPT_VERSION,emotion:input?.emotion,ms:Date.now()-started,...fields});
  try{
    input=await readBody(request);
    const out=await dialogueReply(input,dialogue?.config,{fetchImpl:dialogue?.fetch||fetch});
    record({ok:true,chars_in:String(input.text||'').length,chars_out:out.text.length,...(out.gate==='on'?{passed:out.passed,attempts:out.attempts}:{})});
    return json(out);
  }catch(error){
    const status=error instanceof DialogueError?error.status:error.status;
    record({ok:false,status:status||500,error:error.message});
    if(!status)throw error;
    return json({error:error.message},status);
  }
}
