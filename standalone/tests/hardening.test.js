import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync,mkdirSync,writeFileSync,rmSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {once} from 'node:events';
import {createServer} from 'node:http';
import manifest from '../public/study/manifest.json' with {type:'json'};
import {setPassword} from '../server/auth.mjs';
import {createEchoServer,clientAddress} from '../server/start.mjs';
import {createLimiter} from '../server/limits.mjs';
import worker,{COLLECTION_VERSION} from '../server/worker.js';import {localDatabase} from '../server/local-db.js';import {localAudio} from '../server/local-audio.js';
import {audioResult,hashAudio} from '../audio-utils.js';import {controlsFor} from '../voice-controls.js';import {createInteractiveSession} from '../interactive-sync.js';

const password='correct-test-password-12345';
async function listen(server){server.listen(0,'127.0.0.1');await once(server,'listening');return `http://127.0.0.1:${server.address().port}`;}
async function site(t,options={}){
 const root=mkdtempSync(join(tmpdir(),'echo-limits-')),dataDir=join(root,'data'),clientDir=join(root,'client'),publicDir=join(root,'public');
 mkdirSync(clientDir);mkdirSync(publicDir);writeFileSync(join(clientDir,'index.html'),'ECHO fixture');setPassword(dataDir,password);
 const upstream=createServer((req,res)=>{req.resume();res.setHeader('Content-Type','application/json');res.end('{"event_id":"fixture"}');});
 const server=createEchoServer({dataDir,clientDir,publicDir,speechService:await listen(upstream),...options}),origin=await listen(server);
 t.after(async()=>{for(const s of [server,upstream]){s.closeAllConnections();await new Promise(resolve=>s.close(resolve));}rmSync(root,{recursive:true,force:true});});
 return (path,{method='GET',data,headers={}}={})=>fetch(origin+path,{method,headers:{Origin:origin,'Content-Type':'application/json',...headers},body:data===undefined?undefined:JSON.stringify(data)});
}

test('the client address comes from the nearest proxy entry only when the proxy is trusted',()=>{
 const req={headers:{'x-forwarded-for':'203.0.113.9, 198.51.100.7'},socket:{remoteAddress:'127.0.0.1'}};
 assert.equal(clientAddress(req),'127.0.0.1');assert.equal(clientAddress(req,true),'198.51.100.7');
 assert.equal(clientAddress({headers:{},socket:{remoteAddress:'::1'}},true),'::1');
});

test('the limiter allows a fixed number per window, forgets old requests and caps its memory',()=>{
 let now=0;const allow=createLimiter({limit:2,windowMs:1000,clock:()=>now});
 assert.deepEqual([allow('a'),allow('a'),allow('a'),allow('b')],[true,true,false,true]);now=1001;assert.equal(allow('a'),true);
 const full=createLimiter({limit:1,windowMs:1000,clock:()=>now,maxKeys:1});assert.equal(full('x'),true);assert.equal(full('y'),false);now=3000;assert.equal(full('y'),true);
});

test('login lockout counts each client behind a trusted proxy, and the proxy address otherwise',async t=>{
 for(const [trustProxy,expected] of [[true,200],[false,429]]){
  const call=await site(t,{trustProxy});
  const login=(pass,ip)=>call('/api/auth/login',{method:'POST',data:{password:pass},headers:{'X-Forwarded-For':ip}});
  for(let i=0;i<5;i++)assert.equal((await login('wrong-password-0123456789','203.0.113.1')).status,401);
  assert.equal((await login(password,'203.0.113.1')).status,429);
  assert.equal((await login(password,'203.0.113.2')).status,expected);
 }
});

test('voice synthesis requests and new sessions are limited per client; resuming a session is not',async t=>{
 const call=await site(t,{speechLimit:2,sessionLimit:1});
 const join=()=>call('/api/tts/gradio_api/queue/join',{method:'POST',data:{}});
 assert.deepEqual([(await join()).status,(await join()).status,(await join()).status],[200,200,429]);
 assert.equal((await call('/api/tts/gradio_api/queue/data?session_hash=fixture')).status,200);
 const start=s=>call('/api/interactive/sessions',{method:'POST',data:s,headers:{Authorization:`Bearer ${s.token}`}});
 const first=createInteractiveSession('line','technical_limit',null),second=createInteractiveSession('line','technical_limit',null);first.record_type=second.record_type='technical_test';
 assert.equal((await start(first)).status,200);assert.equal((await start(first)).status,200);assert.equal((await start(second)).status,429);
 const token=crypto.randomUUID().replaceAll('-','')+crypto.randomUUID().replaceAll('-','');
 const study={nickname:'technical_demo',rating_scale:'va-0.01_match-0.5_naturalness-1_v2',participant_id:'TEST-'+crypto.randomUUID().replaceAll('-','').toUpperCase(),study_version:manifest.study_version,collection_version:COLLECTION_VERSION,record_type:'technical_test',group:3,seed:123,eligibility:{comfortable_english:true,headphones:true,previously_used_studio:false},consent:true,consent_utc:new Date().toISOString()};
 assert.equal((await call('/api/study/sessions',{method:'POST',data:study,headers:{Authorization:`Bearer ${token}`}})).status,429);
});

test('the recording archive refuses new WAVs beyond its storage quota and still accepts a retry',async t=>{
 const dir=mkdtempSync(join(tmpdir(),'echo-quota-')),DB=localDatabase(join(dir,'study.sqlite'));t.after(()=>{DB.close();rmSync(dir,{recursive:true,force:true});});
 const env={DB,AUDIO:localAudio(join(dir,'audio')),RESEARCHER_AUTHORIZED:false,AUDIO_QUOTA_BYTES:60000},origin='https://echo.example';
 const session=createInteractiveSession('line','technical_quota',null);session.record_type='technical_test';
 const call=(path,method,body)=>worker.fetch(new Request(origin+path,{method,headers:{Origin:origin,Authorization:`Bearer ${session.token}`,'Content-Type':body instanceof ArrayBuffer?'audio/wav':'application/json'},body:body instanceof ArrayBuffer?body:JSON.stringify(body)}),env,{});
 const samples=Float32Array.from({length:24000},(_,n)=>.1*Math.sin(n*2*Math.PI*150/24000)),wav=audioResult(samples,24000,1).buffer,sha=await hashAudio(wav);
 const turn=order=>({order,engine:'kokoro',emotion:'happy',input_text:'A quota test.',output_text:'A quota test.',controls:controlsFor({engine:'kokoro',emotion:'happy'}),audio_metrics:{},audio_sha256:sha,duration_s:1,elapsed_s:2.5,created_utc:new Date().toISOString()});
 const base=`/api/interactive/sessions/${session.session_id}`;
 assert.equal((await call('/api/interactive/sessions','POST',session)).status,200);
 assert.equal((await call(base+'/turns','POST',{turns:[turn(1),turn(2)]})).status,200);
 assert.equal((await call(base+'/audio/1','PUT',wav)).status,200);
 assert.equal((await call(base+'/audio/2','PUT',wav)).status,507);
 assert.equal((await call(base+'/audio/1','PUT',wav)).status,200);
});
