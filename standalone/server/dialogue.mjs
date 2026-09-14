import {appendFileSync,readFileSync} from 'node:fs';
import {dialogueMessages,rewriteMessages,DIALOGUE_PROMPT_VERSION,unwrapQuotedReply,stripActLabel,PROMPT_VERSIONS,DEFAULT_PROMPT} from './dialogue-prompt.mjs';
import {REPLY_CHECK_VERSION,CHECK_GENERATION,CHECK_FORMAT,replyCheckMessages,parseVerdict,judgeReply,acceptedAttempt} from './reply-check.mjs';
import {QWEN_BACKUP_ALLOWED,QWEN_BACKUP_MODEL} from './llm-backup.mjs';

// ECHO's primary language model is llama3.2:3b served by Ollama (decision 2026-09-11).
export const PRIMARY_MODEL='llama3.2:3b';
// The generation settings the 1.5.0 conversation used, kept so replies stay comparable.
export const GENERATION={temperature:.7,seed:666,max_tokens:150};
// A hosted model that sleeps between study sessions answers again after a wake-up; the page retries at this interval.
export const WAKE_RETRY_S=15;
// The reply check stays off. In the pre-registered 2026-09-13 screen (evidence 2026-09-13-reply-check-prompt-v4-screen) the
// replies it passed were right 81% of the time (85% required) and an exchange took about five times as long.
// ECHO_REPLY_CHECK=on keeps it available for research.
export const DEFAULT_REPLY_CHECK='off';
const STATUS_CACHE_MS=30000;

export class DialogueError extends Error{constructor(status,message,details={}){super(message);this.status=status;this.details=details;}}

const LOOPBACK=/^https?:\/\/(?:127\.0\.0\.1|localhost|\[::1\])(?::\d+)?(?:\/|$)/i;

// ECHO_COHERENCE_GATE: 'off' = option B, the reply comes straight from Ollama (in use since 2026-09-11).
//                      'on'  = option A, the same request goes through ECHO's coherence gate (gate_service.py).
// ECHO_OLLAMA_URL and ECHO_OLLAMA_TOKEN point at a remote Ollama, such as a private Hugging Face Space that sleeps
// when unused. The token is sent as a Bearer header and never reaches the page.
// ECHO_LLM_MODE=embedded, set on the Hugging Face Space, is a local Ollama that starts beside the website and downloads
// its model again after every wake-up; until it answers, the page is told the model is starting.
// ECHO_OLLAMA_AUTOSTART=0 stops `node server/start.mjs` from starting a local Ollama itself when Explore needs it.
export function dialogueConfig(env=process.env){
  const gate=String(env.ECHO_COHERENCE_GATE||'off').trim().toLowerCase();
  if(!['off','on'].includes(gate))throw new Error('ECHO_COHERENCE_GATE must be off or on.');
  const model=env.ECHO_LLM_BACKUP==='1'?QWEN_BACKUP_MODEL:(env.ECHO_OLLAMA_MODEL||PRIMARY_MODEL);
  if(/qwen/i.test(model)&&!QWEN_BACKUP_ALLOWED)throw new Error('The backup language model is locked in this version; unset ECHO_LLM_BACKUP and ECHO_OLLAMA_MODEL.');
  const ollamaUrl=String(env.ECHO_OLLAMA_URL||'http://127.0.0.1:11434').replace(/\/+$/,''),apiKey=String(env.ECHO_OLLAMA_TOKEN||'').trim()||null;
  const remote=Boolean(apiKey)||!LOOPBACK.test(ollamaUrl);
  const embedded=!remote&&String(env.ECHO_LLM_MODE||'').trim().toLowerCase()==='embedded';
  const autostart=!remote&&!embedded&&!['0','off','false','no'].includes(String(env.ECHO_OLLAMA_AUTOSTART||'').trim().toLowerCase());
  // A remote model gets a shorter wait, so a sleeping Space becomes a quick "starting" answer instead of a hung page.
  const timeoutMs=Number(env.ECHO_LLM_TIMEOUT_MS||(remote?45000:120000));
  if(!Number.isFinite(timeoutMs)||timeoutMs<1000)throw new Error('ECHO_LLM_TIMEOUT_MS must be at least 1000.');
  // ECHO_DIALOGUE_PROMPT picks the conversation prompt: v3, or the 2026-09-13 candidates v4a and v4b.
  const prompt=String(env.ECHO_DIALOGUE_PROMPT||DEFAULT_PROMPT).trim().toLowerCase();
  if(!Object.hasOwn(PROMPT_VERSIONS,prompt))throw new Error(`ECHO_DIALOGUE_PROMPT must be one of: ${Object.keys(PROMPT_VERSIONS).join(', ')}.`);
  if(prompt==='v4c'&&gate==='on')throw new Error('The coherence gate cannot run the two-pass prompt v4c; set ECHO_COHERENCE_GATE=off.');
  // ECHO_REPLY_CHECK=on checks each reply against the message and the chosen quadrant and generates a miss again (reply-check.mjs).
  const check=String(env.ECHO_REPLY_CHECK||DEFAULT_REPLY_CHECK).trim().toLowerCase();
  if(!['off','on'].includes(check))throw new Error('ECHO_REPLY_CHECK must be off or on.');
  const checkRetries=Number(env.ECHO_REPLY_CHECK_RETRIES??2);
  if(!Number.isInteger(checkRetries)||checkRetries<0||checkRetries>4)throw new Error('ECHO_REPLY_CHECK_RETRIES must be a whole number from 0 to 4.');
  return {gate,model,timeoutMs,ollamaUrl,gateUrl:String(env.ECHO_GATE_URL||'http://127.0.0.1:8790').replace(/\/+$/,''),apiKey,remote,embedded,autostart,prompt,check,checkRetries};
}

const waking=()=>new DialogueError(503,'The conversation model is starting after a quiet period. ECHO keeps trying; this can take about two minutes.',{waking:true,retry_after_s:WAKE_RETRY_S});

// onUnreachable() returns true when it has started the local Ollama, so the page is told the model is starting.
async function send(fetchImpl,url,{method='POST',payload,apiKey=null,wakes=false,onUnreachable=null,timeoutMs}){
  const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),timeoutMs);
  const headers={...(payload===undefined?{}:{'Content-Type':'application/json'}),...(apiKey?{Authorization:`Bearer ${apiKey}`}:{})};
  try{
    const response=await fetchImpl(url,{method,headers,body:payload===undefined?undefined:JSON.stringify(payload),signal:controller.signal});
    let data=null;try{data=await response.json();}catch{}
    return {response,data};
  }catch{
    if(wakes||onUnreachable?.())throw waking();
    throw new DialogueError(503,'The local language model is not reachable. Start Ollama and try again.');
  }finally{clearTimeout(timer);}
}

// A remote model that is still starting is answered by the hosting proxy: 502/503/504, or a page instead of JSON.
function checkRemote(config,response,data){
  if(!config.remote)return;
  if([502,503,504].includes(response.status)||response.ok&&data===null)throw waking();
  if([401,403].includes(response.status)||response.status===404&&data===null)throw new DialogueError(503,'The conversation model refused this server\'s access settings. Tell the researcher.');
}

const startsOllama=(config,launcher)=>()=>config.autostart&&launcher?.start()===true;

// Error messages never name a model: they reach the page.
export async function dialogueReply(input,config,{fetchImpl=fetch,launcher=null}={}){
  if(!config)throw new DialogueError(503,'Conversation replies are not configured on this server.');
  const variant=config.prompt||DEFAULT_PROMPT,prompt_version=PROMPT_VERSIONS[variant],history=Array.isArray(input?.history)?input.history:[];
  let messages;
  try{messages=dialogueMessages(input?.text,input?.emotion,history,{variant});}
  catch(error){throw new DialogueError(400,error.message);}
  if(config.gate==='on'){
    const {response,data}=await send(fetchImpl,`${config.gateUrl}/v1/gated-reply`,{payload:{messages,emotion:input.emotion,model:config.model,...GENERATION},timeoutMs:config.timeoutMs});
    const text=typeof data?.text==='string'?unwrapQuotedReply(data.text):'';
    if(!response.ok||!text)throw new DialogueError(502,'The coherence gate could not produce a reply. Try again.');
    return {text,gate:'on',prompt_version,passed:data.passed===true,attempts:Array.isArray(data.attempts)?data.attempts.length:0};
  }
  const ask=payload=>send(fetchImpl,`${config.ollamaUrl}/v1/chat/completions`,{payload,apiKey:config.apiKey,wakes:config.remote||config.embedded,onUnreachable:startsOllama(config,launcher),timeoutMs:config.timeoutMs});
  const complete=async(chat,seed)=>{
    const {response,data}=await ask({model:config.model,messages:chat,...GENERATION,seed,stream:false});
    checkRemote(config,response,data);
    // An embedded Ollama answers 404 while it is still downloading the model after a wake-up.
    if(response.status===404){if(config.embedded)throw waking();throw new DialogueError(503,'The language model is not installed in Ollama.');}
    if(!response.ok)throw new DialogueError(502,'The language model could not produce a reply. Try again.');
    const choice=data?.choices?.[0];
    return {content:typeof choice?.message?.content==='string'?choice.message.content:'',finish:choice?.finish_reason};
  };
  const incomplete=()=>new DialogueError(502,'The reply was empty or incomplete. Try a shorter message.');
  const generate=async seed=>{
    let {content,finish}=await complete(messages,seed),draft=null;
    // v4c: the first pass answered the message; the second rewrites that answer into the chosen emotion, with the same seed.
    if(variant==='v4c'){
      draft=unwrapQuotedReply(content);if(!draft||finish==='length')throw incomplete();
      ({content,finish}=await complete(rewriteMessages(input.text,draft,input.emotion),seed));
    }
    // v4b replies begin with a one-word reading of the message, removed before the reply is checked or spoken.
    const {reply,act}=variant==='v4b'?stripActLabel(content):{reply:content,act:null},text=unwrapQuotedReply(reply);
    if(!text||finish==='length')throw incomplete();
    return {text,act,seed,draft};
  };
  const first=await generate(GENERATION.seed);
  if(config.check!=='on')return {text:first.text,gate:'off',prompt_version,...(first.draft?{details:[{seed:first.seed,text:first.text,act:null,draft:first.draft}]}:{})};
  // The reply check (reply-check.mjs): each attempt is checked; a miss is generated again with the next seed. A failure of
  // the check itself, or of a later attempt, never refuses the reply: the best attempt so far is used.
  const attempts=[first],verdicts=[],checkMs=[];
  for(let i=0;;i++){
    const started=Date.now();let verdict=null;
    try{
      const {response,data}=await ask({model:config.model,messages:replyCheckMessages(input.text,attempts[i].text,history),...CHECK_GENERATION,response_format:CHECK_FORMAT,stream:false});
      const parsed=response.ok?parseVerdict(data?.choices?.[0]?.message?.content):null;
      verdict=parsed&&judgeReply(parsed,input.emotion);
    }catch{verdict=null;}
    verdicts.push(verdict);checkMs.push(Date.now()-started);
    if(!verdict||verdict.passed||i>=config.checkRetries)break;
    try{attempts.push(await generate(GENERATION.seed+i+1));}catch{break;}
  }
  const {status,index}=acceptedAttempt(verdicts);
  return {text:attempts[index].text,gate:'off',prompt_version,
    check:{version:REPLY_CHECK_VERSION,status,attempts:verdicts.length,accepted:index,
      verdicts:verdicts.map((v,i)=>v&&{seed:attempts[i].seed,responds:v.responds,feeling:v.feeling,energy:v.energy,quadrant:v.quadrant,passed:v.passed})},
    details:attempts.map((a,i)=>({seed:a.seed,text:a.text,act:a.act,draft:a.draft,check_ms:checkMs[i]}))};
}

// Whether the model answers. Asking a sleeping hosted model also starts it, so the page asks when Explore opens; a local
// Ollama that does not answer is started, and one that answers loads the model before the first message.
export async function dialogueStatus(config,{fetchImpl=fetch,launcher=null}={}){
  if(!config)return {ready:false,waking:false};
  try{
    const {response,data}=await send(fetchImpl,`${config.ollamaUrl}/api/version`,{method:'GET',apiKey:config.apiKey,wakes:config.remote||config.embedded,onUnreachable:startsOllama(config,launcher),timeoutMs:Math.min(config.timeoutMs,8000)});
    checkRemote(config,response,data);
    const ready=response.ok&&typeof data?.version==='string';
    if(ready&&config.autostart)launcher?.preload();
    return {ready,waking:false};
  }catch(error){return {ready:false,waking:error.details?.waking===true};}
}

// One JSON line per reply in the private data folder, so option B's latency and failures can be reviewed; researchers
// download the file from /api/research/dialogue-metrics.jsonl.
export function createMetricsLog(file){
  const log=entry=>{try{appendFileSync(file,JSON.stringify(entry)+'\n',{mode:0o600});}catch(error){console.error('Could not record dialogue metrics:',error.message);}};
  log.read=()=>{try{return readFileSync(file,'utf8');}catch(error){if(error.code==='ENOENT')return '';throw error;}};
  return log;
}

// The page names its conversation, planned message and browser attempt, so a metrics line joins the saved message and its
// generation attempt. Malformed identifiers are left out; they never refuse a reply.
export function metricsLink(input){
  const link={};
  if(typeof input?.session_id==='string'&&/^X-[A-F0-9]{32}$/.test(input.session_id))link.session_id=input.session_id;
  if(Number.isInteger(input?.turn_order)&&input.turn_order>=1&&input.turn_order<=12)link.turn_order=input.turn_order;
  if(typeof input?.attempt_id==='string'&&/^[a-f0-9-]{36}$/.test(input.attempt_id))link.attempt_id=input.attempt_id;
  return link;
}

export async function handleDialogueRequest(request,env,{readBody,json}){
  const started=Date.now(),dialogue=env.DIALOGUE;let input={};
  const record=fields=>dialogue?.log?.({utc:new Date().toISOString(),gate:dialogue?.config?.gate,model:dialogue?.config?.model,prompt_version:PROMPT_VERSIONS[dialogue?.config?.prompt]??DIALOGUE_PROMPT_VERSION,emotion:input?.emotion,ms:Date.now()-started,...metricsLink(input),...fields});
  try{
    input=await readBody(request);
    // Rejected attempts' texts stay in the private metrics line; the page receives the accepted reply and the verdicts only.
    const {details,...out}=await dialogueReply(input,dialogue?.config,{fetchImpl:dialogue?.fetch||fetch,launcher:dialogue?.launcher});
    record({ok:true,chars_in:String(input.text||'').length,chars_out:out.text.length,...(out.gate==='on'?{passed:out.passed,attempts:out.attempts}:{}),
      ...(out.check?{check:{...out.check,replies:details.map(d=>d.text),acts:details.map(d=>d.act),check_ms:details.map(d=>d.check_ms)}}:{}),
      ...(details?.some(d=>d.draft)?{drafts:details.map(d=>d.draft)}:{})});
    return json(out);
  }catch(error){
    const status=error instanceof DialogueError?error.status:error.status;
    record({ok:false,status:status||500,error:error.message,...(error.details?.waking?{waking:true}:{})});
    if(!status)throw error;
    return json({error:error.message,...(error.details||{})},status);
  }
}

// The answer is cached briefly, so pages opening Explore cannot keep a paid hosted model awake by themselves.
export async function handleDialogueStatus(request,env,{json}){
  const dialogue=env.DIALOGUE,cache=dialogue?.status;
  if(cache?.value&&Date.now()-cache.at<STATUS_CACHE_MS)return json(cache.value);
  const value=await dialogueStatus(dialogue?.config,{fetchImpl:dialogue?.fetch||fetch,launcher:dialogue?.launcher});
  if(cache){cache.at=Date.now();cache.value=value;}
  return json(value);
}
