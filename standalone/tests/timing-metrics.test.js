import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync,rmSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {GENERATION_METADATA_VERSION,seconds,queueTracker,visibilityWatch,deviceContext,TIMING_COLUMNS} from '../generation-timing.js';
import {createMetricsLog,dialogueConfig,handleDialogueRequest,metricsLink} from '../server/dialogue.mjs';
import {explorationCSV} from '../server/interactive.js';
import worker from '../server/worker.js';
import {localDatabase} from '../server/local-db.js';
import {localAudio} from '../server/local-audio.js';
import {createInteractiveSession,InteractiveSync} from '../interactive-sync.js';
import {NeuralClient} from '../neural-client.js';
import {requestReply} from '../dialogue-client.js';
import {RemoteSpeechClient} from '../remote-speech.js';
import {controlsFor} from '../voice-controls.js';

const origin='https://echo.example';
const cells=line=>[...line.matchAll(/"((?:[^"]|"")*)"/g)].map(m=>m[1].replaceAll('""','"'));
const ollamaReply=content=>({ok:true,status:200,json:async()=>({choices:[{message:{content},finish_reason:'stop'}]})});
const attemptId='0f8fad5b-d9cb-469f-a165-70867728950e';
function database(t){
  const dir=mkdtempSync(join(tmpdir(),'echo-timing-')),DB=localDatabase(join(dir,'study.sqlite'));
  t.after(()=>{DB.close();rmSync(dir,{recursive:true,force:true});});
  const env={DB,AUDIO:localAudio(join(dir,'audio')),RESEARCHER_AUTHORIZED:false};
  return {dir,env,fetcher:(path,options={})=>worker.fetch(new Request(origin+path,{...options,headers:{Origin:origin,...options.headers}}),env,{})};
}

test('durations become seconds with millisecond resolution; invalid ones become null',()=>{
  assert.equal(GENERATION_METADATA_VERSION,'echo-generation-v2');
  assert.equal(seconds(1234.4),1.234);assert.equal(seconds(0),0);
  for(const bad of [-1,NaN,Infinity,undefined,'5'])assert.equal(seconds(bad),null);
});

test('the queue ends at the last pending status, where work on the speech service begins',()=>{
  const times=[150,400],queue=queueTracker(100,()=>times.shift());
  queue.status({stage:'pending',position:1});queue.status({stage:'pending',position:0});queue.status({stage:'complete'});
  assert.deepEqual(queue.summary(900),{queue_s:.3,service_processing_s:.5,max_queue_position:2});
  assert.deepEqual(queueTracker(0,()=>0).summary(50),{queue_s:null,service_processing_s:null,max_queue_position:null});
});

test('a page hidden at any moment of a request is remembered, and the watch removes its listener',()=>{
  const listeners=new Set(),doc={visibilityState:'visible',addEventListener:(_,f)=>listeners.add(f),removeEventListener:(_,f)=>listeners.delete(f)};
  const watch=visibilityWatch(doc);
  doc.visibilityState='hidden';listeners.forEach(f=>f());doc.visibilityState='visible';listeners.forEach(f=>f());
  assert.equal(watch.stop(),true);assert.equal(listeners.size,0);
  assert.equal(visibilityWatch(doc).stop(),false);
  assert.equal(visibilityWatch(null).stop(),null);
});

test('device context keeps only coarse classes the browser reports',()=>{
  assert.deepEqual(deviceContext({hardwareConcurrency:8,deviceMemory:4,connection:{effectiveType:'4g'},userAgent:'Mozilla/5.0'}),{hardware_concurrency:8,device_memory_gb:4,network_effective_type:'4g'});
  const none={hardware_concurrency:null,device_memory_gb:null,network_effective_type:null};
  assert.deepEqual(deviceContext({hardwareConcurrency:0,deviceMemory:'lots',connection:{effectiveType:'wifi'}}),none);
  assert.deepEqual(deviceContext({}),none);
});

test('a reply metrics line names its conversation, planned message and attempt when the page sends valid identifiers',async()=>{
  const link={session_id:'X-'+'A'.repeat(32),turn_order:3,attempt_id:attemptId};
  assert.deepEqual(metricsLink(link),link);
  assert.deepEqual(metricsLink({session_id:'P-1234',turn_order:13,attempt_id:'not-an-attempt'}),{});
  assert.deepEqual(metricsLink(undefined),{});
  const lines=[],json=(value,status=200)=>({status,value});
  const env={DIALOGUE:{config:dialogueConfig({}),log:e=>lines.push(e),fetch:async()=>ollamaReply('Fine.')}};
  const reply=await handleDialogueRequest({},env,{readBody:async()=>({text:'Help me prepare for a busy study day.',emotion:'calm',history:[],...link}),json});
  assert.equal(reply.status,200);assert.equal(reply.value.session_id,undefined);
  assert.deepEqual([lines[0].ok,lines[0].session_id,lines[0].turn_order,lines[0].attempt_id],[true,link.session_id,3,attemptId]);
  assert.ok(Number.isFinite(lines[0].ms));
});

test('the page client sends the reply identifiers with its request',async()=>{
  const bodies=[],fetchImpl=async(_,init)=>{bodies.push(JSON.parse(init.body));return {ok:true,json:async()=>({text:'Hello.',gate:'off'})};};
  const link={session_id:'X-'+'B'.repeat(32),turn_order:1,attempt_id:attemptId};
  await requestReply({text:'Hi there.',emotion:'happy',history:[],link},{fetchImpl});
  assert.deepEqual(bodies[0],{text:'Hi there.',emotion:'happy',history:[],...link});
});

test('researchers download the reply metrics file; everyone else is refused',async t=>{
  const {dir,env,fetcher}=database(t),log=createMetricsLog(join(dir,'dialogue-metrics.jsonl'));
  assert.equal(log.read(),'');log({ok:true,ms:12});env.DIALOGUE={log};
  const path='/api/research/dialogue-metrics.jsonl';
  assert.equal((await fetcher(path)).status,401);
  env.RESEARCHER_AUTHORIZED=true;const response=await fetcher(path);
  assert.equal(response.status,200);assert.match(response.headers.get('content-disposition'),/echo-dialogue-metrics\.jsonl/);
  assert.deepEqual((await response.text()).trim().split('\n').map(line=>JSON.parse(line)),[{ok:true,ms:12}]);
  delete env.DIALOGUE;assert.equal((await fetcher(path)).status,404);
});

test('the exploratory CSV appends rating time and flattened timing columns; older messages leave them empty',()=>{
  const generation_metadata={version:'echo-generation-v2',
    timing:{engine_location:'speech_service',connect_s:.1,queue_s:.3,service_processing_s:.5,service_s:.8,max_queue_position:2,download_s:.1,browser_processing_s:.1,total_s:1.2,first_request_for_engine_in_page:true,page_hidden:false},
    dialogue:{prompt_version:'echo-dialogue-v3',gate:'off',attempt_id:attemptId,reply_wait_s:1.7,model_start_retries:0},
    exchange:{end_to_end_s:3.1,page_hidden:false},client:{hardware_concurrency:8,device_memory_gb:4,network_effective_type:'4g'}};
  const row={session_id:'X-'+'C'.repeat(32),nickname:'timing_check',mode:'explore',record_type:'technical_test',turn_order:1,engine:'chatterbox',emotion:'calm',input_text:'Hi',output_text:'Hello',created_utc:'2026-09-13T20:00:00.000Z',
    turn_json:JSON.stringify({duration_s:2,elapsed_s:1.2,generation_metadata}),rating_json:JSON.stringify({valence:.1,arousal:.2,naturalness:4,target_match:3.5,elapsed_s:7.5}),audio_stored_utc:null};
  const [header,line]=explorationCSV([row]).trim().split('\r\n'),names=header.split(','),value=Object.fromEntries(names.map((n,i)=>[n,cells(line)[i]]));
  assert.deepEqual(names.slice(-TIMING_COLUMNS.length-4,-4),TIMING_COLUMNS);
  assert.deepEqual(['elapsed_s','rating_elapsed_s','tts_queue_s','tts_service_processing_s','reply_wait_s','reply_attempt_id','exchange_end_to_end_s','tts_cold_start','network_effective_type','generation_metadata_version'].map(k=>value[k]),
    ['1.2','7.5','0.3','0.5','1.7',attemptId,'3.1','','4g','echo-generation-v2']);
  const older=explorationCSV([{...row,turn_json:JSON.stringify({duration_s:2,elapsed_s:1.2,generation_metadata:{version:'echo-generation-v1'}}),rating_json:null}]).trim().split('\r\n')[1];
  assert.equal(cells(older).length,names.length);
});

test('the Kokoro client marks whether a new worker was started for the request',async()=>{
  let current;const client=new NeuralClient(()=>current={postMessage(d){this.id=d.id;},terminate(){}},5000);
  const first=client.run({},()=>{});current.onmessage({data:{id:current.id,type:'result',result:{timing:{cold_start:true}}}});
  assert.deepEqual((await first).timing,{cold_start:true,worker_created:true});
  const second=client.run({},()=>{});current.onmessage({data:{id:current.id,type:'result',result:{timing:{cold_start:false}}}});
  assert.equal((await second).timing.worker_created,false);
  const third=client.run({},()=>{});current.onmessage({data:{id:current.id,type:'result',result:3}});assert.equal(await third,3);
});

test('a server voice reports where its time went: connection, queue, service, download and browser processing',async()=>{
  const times=[0,100,150,400,900,1000,1100],samples=Float32Array.from({length:24000},(_,n)=>.1*Math.sin(n*2*Math.PI*150/24000));
  const params=controlsFor({engine:'chatterbox',emotion:'happy'}),meta={engine:'chatterbox',condition:'preset',duration_s:1};
  const events=[{type:'status',stage:'pending',position:1},{type:'status',stage:'pending',position:0},{type:'data',data:[{url:'/api/tts/gradio_api/file=voice.wav'},meta]},{type:'status',stage:'complete'}];
  const job={async *[Symbol.asyncIterator](){yield* events;},cancel(){}};
  const client=new RemoteSpeechClient({now:()=>times.shift(),connect:async()=>({submit:()=>job,close(){},config:{}}),
    fetchImpl:async()=>({ok:true,arrayBuffer:async()=>new ArrayBuffer(8)}),
    audioContext:()=>({decodeAudioData:async()=>({numberOfChannels:1,sampleRate:24000,getChannelData:()=>samples}),close:async()=>{}})});
  const result=await client.run({text:'The package is on the table near the window.',params},()=>{});
  assert.deepEqual(result.timing,{engine_location:'speech_service',connect_s:.1,queue_s:.3,service_processing_s:.5,max_queue_position:2,service_s:.8,download_s:.1,browser_processing_s:.1});
  assert.equal(result.service_metadata,meta);assert.equal(times.length,0);
});

test('a successful reply diagnostic waits for the message save, and the server keeps stage dialogue',async t=>{
  const {env,fetcher}=database(t);let requests=0;
  const counted=(path,options)=>{requests++;return fetcher(path,options);};
  const session=createInteractiveSession('explore','timing_check','kokoro');session.record_type='technical_test';
  const client=new InteractiveSync(session,{fetcher:counted});
  const event={attempt_id:attemptId,engine:'kokoro',emotion:'calm',status:'success',stage:'dialogue',elapsed_s:1.7,created_utc:new Date().toISOString(),turn_order:null};
  await client.attempt(event,{sync:false});assert.equal(requests,0);
  await client.sync();assert.ok(requests>0);
  env.RESEARCHER_AUTHORIZED=true;
  const diagnostics=await (await fetcher('/api/research/diagnostics.json')).json();
  assert.deepEqual(diagnostics.attempts.map(a=>[a.stage,a.status,a.attempt_id]),[['dialogue','success',attemptId]]);
  assert.match(diagnostics.scope,/conversation replies \(stage dialogue\)/);
});
