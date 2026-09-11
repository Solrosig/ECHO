import test from 'node:test';
import assert from 'node:assert/strict';
import {dialogueConfig,dialogueReply,handleDialogueRequest,DialogueError,GENERATION,PRIMARY_MODEL} from '../server/dialogue.mjs';
import {QWEN_BACKUP_ALLOWED} from '../server/llm-backup.mjs';
import {dialogueMessages} from '../voice-controls.js';

const input={text:'The meeting was moved to a different room.',emotion:'calm',history:[]};
const ollamaReply=(content,finish='stop')=>({ok:true,status:200,json:async()=>({choices:[{message:{content},finish_reason:finish}]})});
function recorder(response){const calls=[];return {calls,fetchImpl:async(url,init)=>{calls.push({url,body:JSON.parse(init.body)});return response;}};}
const offline=async()=>{throw new TypeError('fetch failed');};
const namesAModel=message=>/llama|qwen|ollama pull/i.test(message);

test('defaults: llama3.2:3b through local Ollama with the coherence gate off',()=>{
  assert.equal(PRIMARY_MODEL,'llama3.2:3b');
  assert.deepEqual(dialogueConfig({}),{gate:'off',model:'llama3.2:3b',timeoutMs:120000,ollamaUrl:'http://127.0.0.1:11434',gateUrl:'http://127.0.0.1:8790'});
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

test('option B asks Ollama once, with the shared prompt and the 1.5.0 generation settings',async()=>{
  const {calls,fetchImpl}=recorder(ollamaReply('  A calm reply.  '));
  assert.deepEqual(await dialogueReply(input,dialogueConfig({}),{fetchImpl}),{text:'A calm reply.',gate:'off'});
  assert.equal(calls.length,1);
  assert.equal(calls[0].url,'http://127.0.0.1:11434/v1/chat/completions');
  assert.deepEqual(calls[0].body,{model:'llama3.2:3b',messages:dialogueMessages(input.text,input.emotion,[]),...GENERATION,stream:false});
});

test('option A sends the same messages and settings to the coherence-gate service',async()=>{
  const {calls,fetchImpl}=recorder({ok:true,status:200,json:async()=>({text:' Gated reply. ',passed:false,attempts:[{},{},{}]})});
  assert.deepEqual(await dialogueReply(input,dialogueConfig({ECHO_COHERENCE_GATE:'on'}),{fetchImpl}),{text:'Gated reply.',gate:'on',passed:false,attempts:3});
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
  await expect(dialogueReply({...input,emotion:'angry'},config,{fetchImpl:offline}),400);
  await expect(dialogueReply(input,undefined,{fetchImpl:offline}),503);
  await expect(dialogueReply(input,dialogueConfig({ECHO_COHERENCE_GATE:'on'}),{fetchImpl:async()=>({ok:false,status:502,json:async()=>({error:'x'})})}),502);
});

test('the request handler records one metrics line per reply, including failures',async()=>{
  const lines=[],json=(value,status=200)=>({status,value});
  const env={DIALOGUE:{config:dialogueConfig({}),log:e=>lines.push(e),fetch:async()=>ollamaReply('Fine.')}};
  assert.deepEqual(await handleDialogueRequest({},env,{readBody:async()=>input,json}),{status:200,value:{text:'Fine.',gate:'off'}});
  env.DIALOGUE.fetch=offline;
  assert.equal((await handleDialogueRequest({},env,{readBody:async()=>input,json})).status,503);
  assert.equal(lines.length,2);
  assert.deepEqual([lines[0].ok,lines[0].gate,lines[0].model,lines[0].emotion,lines[0].chars_out],[true,'off','llama3.2:3b','calm',5]);
  assert.deepEqual([lines[1].ok,lines[1].status],[false,503]);
});
