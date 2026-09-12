import test from 'node:test';
import assert from 'node:assert/strict';
import {EventEmitter} from 'node:events';
import {createOllamaLauncher,ollamaCommand,START_RETRY_MS,PRELOAD_INTERVAL_MS} from '../server/ollama-launcher.mjs';
import {dialogueConfig,dialogueReply,dialogueStatus,handleDialogueRequest,handleDialogueStatus} from '../server/dialogue.mjs';

const quiet={log(){},error(){}};
const input={text:'Hello there.',emotion:'calm',history:[]};
const offline=async()=>{throw new TypeError('fetch failed');};
const settle=async(done,rounds=50)=>{for(let i=0;i<rounds&&!done();i++)await new Promise(resolve=>setTimeout(resolve,0));};
function fakeSpawn(){
  const calls=[];
  const spawn=(command,args,options)=>{const child=Object.assign(new EventEmitter(),{unref(){child.unrefed=true;}});calls.push({command,args,options,child});return child;};
  return {spawn,calls};
}

test('the Ollama command comes from ECHO_OLLAMA_EXE, the Windows install folder, or the PATH',()=>{
  assert.equal(ollamaCommand({ECHO_OLLAMA_EXE:'D:\\Tools\\ollama.exe',LOCALAPPDATA:'C:\\Users\\a\\AppData\\Local'},'win32'),'D:\\Tools\\ollama.exe');
  assert.match(ollamaCommand({LOCALAPPDATA:'C:\\Users\\a\\AppData\\Local'},'win32'),/Programs[\\/]Ollama[\\/]ollama\.exe$/);
  assert.equal(ollamaCommand({},'linux'),'ollama');
});

test('autostart applies only to a local Ollama the website manages, and ECHO_OLLAMA_AUTOSTART=0 turns it off',()=>{
  assert.equal(dialogueConfig({}).autostart,true);
  for(const value of ['0','off','false',' OFF '])assert.equal(dialogueConfig({ECHO_OLLAMA_AUTOSTART:value}).autostart,false);
  assert.equal(dialogueConfig({ECHO_OLLAMA_URL:'https://someone-echo-llm.hf.space'}).autostart,false);
  assert.equal(dialogueConfig({ECHO_OLLAMA_TOKEN:'hf_example'}).autostart,false);
  assert.equal(dialogueConfig({ECHO_LLM_MODE:'embedded'}).autostart,false);
});

test('the launcher starts Ollama at most once a minute on the configured port, then loads the model when it answers',async()=>{
  let clock=1000,up=false;const {spawn,calls}=fakeSpawn(),requests=[];
  const fetchImpl=async(url,init={})=>{requests.push({method:init.method||'GET',url,body:init.body});if(!up)throw new TypeError('fetch failed');return {ok:true,text:async()=>'{}'};};
  const generate=()=>requests.filter(r=>r.url.endsWith('/api/generate'));
  const launcher=createOllamaLauncher({url:'http://127.0.0.1:11500',model:'llama3.2:3b',command:'ollama-test',spawn,fetchImpl,now:()=>clock,delay:async()=>{up=true;},log:quiet});
  assert.equal(launcher.start(),true);
  const [first]=calls;
  assert.deepEqual([first.command,first.args,first.options.detached,first.options.windowsHide,first.options.stdio,first.options.env.OLLAMA_HOST,first.child.unrefed],['ollama-test',['serve'],true,true,'ignore','127.0.0.1:11500',true]);
  await settle(()=>generate().length>0);
  assert.deepEqual(generate().map(r=>JSON.parse(r.body)),[{model:'llama3.2:3b'}]);
  assert.equal(launcher.start(),true);assert.equal(calls.length,1);
  clock+=START_RETRY_MS;assert.equal(launcher.start(),true);assert.equal(calls.length,2);
  launcher.preload();clock+=PRELOAD_INTERVAL_MS;launcher.preload();
  await settle(()=>false,20);
  assert.equal(generate().length,2);
});

test('an Ollama that is not installed is reported and not started again',async()=>{
  const {spawn,calls}=fakeSpawn(),errors=[];
  const launcher=createOllamaLauncher({url:'http://127.0.0.1:11434',model:'llama3.2:3b',command:'missing-ollama',spawn,fetchImpl:offline,now:()=>0,delay:async()=>{},log:{log(){},error:message=>errors.push(message)}});
  assert.equal(launcher.start(),true);
  calls[0].child.emit('error',Object.assign(new Error('spawn missing-ollama ENOENT'),{code:'ENOENT'}));
  assert.equal(launcher.missing,true);assert.equal(launcher.start(),false);assert.equal(calls.length,1);assert.match(errors[0],/not found at missing-ollama/);
  const throwing=createOllamaLauncher({url:'http://127.0.0.1:11434',model:'llama3.2:3b',spawn:()=>{throw new Error('blocked');},fetchImpl:offline,log:quiet});
  assert.equal(throwing.start(),false);
});

test('Explore starts the local Ollama when it does not answer, and the page is told the model is starting',async()=>{
  const config=dialogueConfig({});let starts=0;const launcher={start(){starts++;return true;},preload(){}};
  await assert.rejects(dialogueReply(input,config,{fetchImpl:offline,launcher}),e=>e.status===503&&e.details.waking===true);
  assert.equal(starts,1);
  assert.deepEqual(await dialogueStatus(config,{fetchImpl:offline,launcher}),{ready:false,waking:true});assert.equal(starts,2);
  const lines=[],env={DIALOGUE:{config,log:entry=>lines.push(entry),fetch:offline,launcher}};
  const answer=await handleDialogueRequest({},env,{readBody:async()=>input,json:(value,status=200)=>({value,status})});
  assert.equal(answer.status,503);assert.equal(answer.value.waking,true);assert.equal(lines[0].waking,true);assert.equal(starts,3);
  await assert.rejects(dialogueReply(input,config,{fetchImpl:offline,launcher:{start:()=>false,preload(){}}}),e=>e.status===503&&e.details.waking===undefined&&/Start Ollama/.test(e.message));
  await assert.rejects(dialogueReply(input,dialogueConfig({ECHO_OLLAMA_AUTOSTART:'0'}),{fetchImpl:offline,launcher}),/Start Ollama/);
  await assert.rejects(dialogueReply(input,dialogueConfig({ECHO_COHERENCE_GATE:'on'}),{fetchImpl:offline,launcher}),/Start Ollama/);
  assert.equal(starts,3);
});

test('opening Explore loads the model when the local Ollama already answers',async()=>{
  let preloads=0;const launcher={start(){throw new Error('Ollama is already running.');},preload(){preloads++;}};
  const fetchImpl=async()=>({ok:true,status:200,json:async()=>({version:'0.30.11'})});
  const env={DIALOGUE:{config:dialogueConfig({}),status:{at:0,value:null},fetch:fetchImpl,launcher}};
  assert.deepEqual(await handleDialogueStatus({},env,{json:value=>value}),{ready:true,waking:false});assert.equal(preloads,1);
  assert.deepEqual(await dialogueStatus(dialogueConfig({ECHO_OLLAMA_AUTOSTART:'0'}),{fetchImpl,launcher}),{ready:true,waking:false});assert.equal(preloads,1);
});
