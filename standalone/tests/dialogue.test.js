import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {dialogueConfig,dialogueReply,dialogueStatus,handleDialogueRequest,handleDialogueStatus,DialogueError,GENERATION,PRIMARY_MODEL,WAKE_RETRY_S} from '../server/dialogue.mjs';
import {QWEN_BACKUP_ALLOWED} from '../server/llm-backup.mjs';
import {dialogueMessages,DIALOGUE_PROMPT_VERSION,unwrapQuotedReply} from '../server/dialogue-prompt.mjs';

const input={text:'The meeting was moved to a different room.',emotion:'calm',history:[]};
const ollamaReply=(content,finish='stop')=>({ok:true,status:200,json:async()=>({choices:[{message:{content},finish_reason:finish}]})});
const htmlPage=status=>({ok:status<400,status,json:async()=>{throw new SyntaxError('Unexpected token <');}});
function recorder(response){const calls=[];return {calls,fetchImpl:async(url,init)=>{calls.push({url,body:JSON.parse(init.body)});return response;}};}
const offline=async()=>{throw new TypeError('fetch failed');};
const namesAModel=message=>/llama3|qwen/i.test(message);
const remoteEnv={ECHO_OLLAMA_URL:'https://owner-echo-llm.hf.space/',ECHO_OLLAMA_TOKEN:' hf_test_token '};

test('defaults: llama3.2:3b through local Ollama with the coherence gate off',()=>{
  assert.equal(PRIMARY_MODEL,'llama3.2:3b');
  assert.deepEqual(dialogueConfig({}),{gate:'off',model:'llama3.2:3b',timeoutMs:120000,ollamaUrl:'http://127.0.0.1:11434',gateUrl:'http://127.0.0.1:8790',apiKey:null,remote:false});
});

test('the gate switch accepts only off or on',()=>{
  assert.equal(dialogueConfig({ECHO_COHERENCE_GATE:' ON '}).gate,'on');
  assert.throws(()=>dialogueConfig({ECHO_COHERENCE_GATE:'maybe'}),/off or on/);
});

test('the Qwen backup stays locked until a dedicated commit allows it',()=>{
  assert.equal(QWEN_BACKUP_ALLOWED,false);
  assert.throws(()=>dialogueConfig({ECHO_LLM_BACKUP:'1'}),/locked/);
  assert.throws(()=>dialogueConfig({ECHO_OLLAMA_MODEL:'qwen2.5:1.5b'}),/locked/);
});

test('the server prompt names the chosen emotion in ECHO quadrant wording, gives one example and keeps the safety rules',()=>{
  const wording={happy:'HAPPY and ENERGETIC',upset:'UPSET and AGITATED',sad:'SAD and SUBDUED',calm:'CALM and CONTENT'};
  for(const [emotion,label] of Object.entries(wording)){
    const [system,user]=dialogueMessages('The bus was late this morning.',emotion,[]);
    assert.equal(system.role,'system');assert.ok(system.content.includes(label));
    assert.match(system.content,/even when the message is ordinary or neutral/);
    assert.match(system.content,/For example, to the message "It is supposed to rain tomorrow afternoon\." a reply with this emotion could be: "[^"]+" Do not reuse the example's words\./);
    assert.match(system.content,/Never infer, diagnose or change the user's emotional target\. Do not invent facts\./);
    assert.match(system.content,/maximum 45 words/);assert.doesNotMatch(system.content,/helpful/);
    assert.deepEqual(user,{role:'user',content:'The bus was late this morning.'});
  }
  assert.match(dialogueMessages('Hi.','happy')[0].content,/at least one exclamation mark/);
  assert.match(dialogueMessages('Hi.','sad')[0].content,/without exclamation marks/);
  const history=Array.from({length:9},(_,i)=>({role:i===4?'system':i%2?'assistant':'user',content:'x'.repeat(900)}));
  const messages=dialogueMessages('Hi.','calm',history);
  assert.equal(messages.length,7);assert.ok(messages.slice(1,-1).every(m=>m.role!=='system'&&m.content.length===800));
  assert.throws(()=>dialogueMessages('','calm'),/1–800/);assert.throws(()=>dialogueMessages('Hi.','angry'),/Choose an emotion/);
  assert.equal(DIALOGUE_PROMPT_VERSION,'echo-dialogue-v3');
});

test('only a quotation-mark pair around the whole reply is removed',()=>{
  assert.equal(unwrapQuotedReply(' "Looks like we are all set!" '),'Looks like we are all set!');
  assert.equal(unwrapQuotedReply('“Great news!”'),'Great news!');
  for(const kept of ['"Wow," she said.','"Yes" and "no"','She said "hi"','Plain reply.','"'])assert.equal(unwrapQuotedReply(kept),kept);
});

test('the frozen 1.5.0 prompt file keeps the hash the protocol freeze records',()=>{
  const hash=createHash('sha256').update(readFileSync(new URL('../voice-controls.js',import.meta.url))).digest('hex');
  const freeze=readFileSync(new URL('../research-bundle/current-phase/PROTOCOL_FREEZE_V2.json',import.meta.url),'utf8');
  assert.match(freeze,new RegExp(`"voice-controls\\.js":\\s*"${hash}"`));
});

test('option B asks Ollama once, with the server prompt and the 1.5.0 generation settings',async()=>{
  const {calls,fetchImpl}=recorder(ollamaReply('  "A calm reply."  '));
  assert.deepEqual(await dialogueReply(input,dialogueConfig({}),{fetchImpl}),{text:'A calm reply.',gate:'off',prompt_version:DIALOGUE_PROMPT_VERSION});
  assert.equal(calls.length,1);
  assert.equal(calls[0].url,'http://127.0.0.1:11434/v1/chat/completions');
  assert.deepEqual(calls[0].body,{model:'llama3.2:3b',messages:dialogueMessages(input.text,input.emotion,[]),...GENERATION,stream:false});
});

test('option A sends the same messages and settings to the coherence-gate service',async()=>{
  const {calls,fetchImpl}=recorder({ok:true,status:200,json:async()=>({text:' "Gated reply." ',passed:false,attempts:[{},{},{}]})});
  assert.deepEqual(await dialogueReply(input,dialogueConfig({ECHO_COHERENCE_GATE:'on'}),{fetchImpl}),{text:'Gated reply.',gate:'on',prompt_version:DIALOGUE_PROMPT_VERSION,passed:false,attempts:3});
  assert.equal(calls[0].url,'http://127.0.0.1:8790/v1/gated-reply');
  assert.deepEqual(calls[0].body,{messages:dialogueMessages(input.text,input.emotion,[]),emotion:'calm',model:'llama3.2:3b',...GENERATION});
});

test('failures map to clear statuses and never name a model',async()=>{
  const config=dialogueConfig({});
  const expect=(promise,status)=>assert.rejects(promise,e=>e instanceof DialogueError&&e.status===status&&!namesAModel(e.message));
  await expect(dialogueReply(input,config,{fetchImpl:offline}),503);
  await expect(dialogueReply(input,config,{fetchImpl:async()=>({ok:false,status:404,json:async()=>({})})}),503);
  await expect(dialogueReply(input,config,{fetchImpl:async()=>({ok:false,status:500,json:async()=>({})})}),502);
  await expect(dialogueReply(input,config,{fetchImpl:async()=>ollamaReply('cut off','length')}),502);
  await expect(dialogueReply(input,config,{fetchImpl:async()=>ollamaReply('""')}),502);
  await expect(dialogueReply({...input,emotion:'angry'},config,{fetchImpl:offline}),400);
  await expect(dialogueReply(input,undefined,{fetchImpl:offline}),503);
  await expect(dialogueReply(input,dialogueConfig({ECHO_COHERENCE_GATE:'on'}),{fetchImpl:async()=>({ok:false,status:502,json:async()=>({error:'x'})})}),502);
});

test('a remote model gets the token and a shorter timeout, and one that is asleep reads as starting',async()=>{
  const config=dialogueConfig(remoteEnv);
  assert.deepEqual([config.ollamaUrl,config.apiKey,config.remote,config.timeoutMs],['https://owner-echo-llm.hf.space','hf_test_token',true,45000]);
  const seen=[];
  assert.equal((await dialogueReply(input,config,{fetchImpl:async(url,init)=>{seen.push([url,init.headers.Authorization]);return ollamaReply('Ready.');}})).text,'Ready.');
  assert.deepEqual(seen,[['https://owner-echo-llm.hf.space/v1/chat/completions','Bearer hf_test_token']]);
  const starting=e=>e instanceof DialogueError&&e.status===503&&e.details.waking===true&&e.details.retry_after_s===WAKE_RETRY_S&&!e.message.includes('hf_test_token')&&!namesAModel(e.message);
  for(const fetchImpl of [offline,async()=>htmlPage(503),async()=>htmlPage(504),async()=>htmlPage(200)])await assert.rejects(dialogueReply(input,config,{fetchImpl}),starting);
  await assert.rejects(dialogueReply(input,config,{fetchImpl:async()=>({ok:false,status:401,json:async()=>({error:'Invalid credentials'})})}),e=>e.status===503&&!e.details.waking&&/access settings/.test(e.message));
  await assert.rejects(dialogueReply(input,config,{fetchImpl:async()=>htmlPage(404)}),e=>e.status===503&&/access settings/.test(e.message));
  await assert.rejects(dialogueReply(input,dialogueConfig({}),{fetchImpl:offline}),e=>e.status===503&&e.details.waking===undefined&&/Start Ollama/.test(e.message));
});

test('the status check wakes a sleeping remote model, is cached briefly and sends the token only to the model',async()=>{
  let calls=0,ready=false;
  const env={DIALOGUE:{config:dialogueConfig(remoteEnv),status:{at:0,value:null},fetch:async(url,init)=>{
    calls++;assert.equal(url,'https://owner-echo-llm.hf.space/api/version');assert.equal(init.headers.Authorization,'Bearer hf_test_token');
    return ready?{ok:true,status:200,json:async()=>({version:'0.30.11'})}:htmlPage(503);
  }}};
  const json=value=>value;
  assert.deepEqual(await handleDialogueStatus({},env,{json}),{ready:false,waking:true});
  ready=true;assert.deepEqual(await handleDialogueStatus({},env,{json}),{ready:false,waking:true});assert.equal(calls,1);
  env.DIALOGUE.status.at=0;assert.deepEqual(await handleDialogueStatus({},env,{json}),{ready:true,waking:false});assert.equal(calls,2);
  assert.deepEqual(await dialogueStatus(dialogueConfig({}),{fetchImpl:offline}),{ready:false,waking:false});
  assert.deepEqual(await dialogueStatus(undefined),{ready:false,waking:false});
});

test('the request handler records one metrics line per reply, including failures and wake-ups',async()=>{
  const lines=[],json=(value,status=200)=>({status,value});
  const env={DIALOGUE:{config:dialogueConfig({}),log:e=>lines.push(e),fetch:async()=>ollamaReply('Fine.')}};
  assert.deepEqual(await handleDialogueRequest({},env,{readBody:async()=>input,json}),{status:200,value:{text:'Fine.',gate:'off',prompt_version:DIALOGUE_PROMPT_VERSION}});
  env.DIALOGUE.fetch=offline;
  assert.equal((await handleDialogueRequest({},env,{readBody:async()=>input,json})).status,503);
  env.DIALOGUE.config=dialogueConfig(remoteEnv);
  const asleep=await handleDialogueRequest({},env,{readBody:async()=>input,json});
  assert.deepEqual([asleep.status,asleep.value.waking,asleep.value.retry_after_s],[503,true,WAKE_RETRY_S]);
  assert.equal(lines.length,3);
  assert.deepEqual([lines[0].ok,lines[0].gate,lines[0].model,lines[0].prompt_version,lines[0].emotion,lines[0].chars_out],[true,'off','llama3.2:3b','echo-dialogue-v3','calm',5]);
  assert.deepEqual([lines[1].ok,lines[1].status,lines[1].waking],[false,503,undefined]);
  assert.deepEqual([lines[2].ok,lines[2].status,lines[2].waking],[false,503,true]);
  assert.ok(lines.every(l=>!JSON.stringify(l).includes('hf_test_token')));
});
