import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync,mkdirSync,writeFileSync,readFileSync,rmSync,symlinkSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {once} from 'node:events';
import {request as httpRequest} from 'node:http';
import {execFileSync} from 'node:child_process';
import {DatabaseSync} from 'node:sqlite';
import {setPassword,createAuth} from '../server/auth.mjs';
import {createEchoServer} from '../server/start.mjs';
import {COLLECTION_VERSION} from '../server/worker.js';
import {makeTrials} from '../study-session.js';
import {QWEN_REVISION} from '../server/llm-backup.mjs';
import manifest from '../public/study/manifest.json' with {type:'json'};
const password='correct-test-password-12345';
async function fixture(t){
 const root=mkdtempSync(join(tmpdir(),'echo-portable-'));const dataDir=join(root,'data'),clientDir=join(root,'client'),publicDir=join(root,'public');
 mkdirSync(clientDir);mkdirSync(publicDir);writeFileSync(join(clientDir,'index.html'),'ECHO fixture');writeFileSync(join(clientDir,'research.html'),'Researcher password');writeFileSync(join(publicDir,'sample.wav'),'0123456789');setPassword(dataDir,password);
 let server,origin;async function start(){server=createEchoServer({dataDir,clientDir,publicDir});server.listen(0,'127.0.0.1');await once(server,'listening');origin=`http://127.0.0.1:${server.address().port}`;}
 async function stop(){await new Promise(resolve=>{server.close(resolve);server.closeAllConnections();});}
 await start();t.after(async()=>{await stop();rmSync(root,{recursive:true,force:true});});
 const call=(path,{method='GET',data,headers={}}={})=>fetch(origin+path,{method,headers:{Origin:origin,'Content-Type':'application/json',...headers},body:data===undefined?undefined:JSON.stringify(data)});
 return {root,dataDir,clientDir,publicDir,call,stop,start,get origin(){return origin;}};
}
test('fresh standalone HTTP server: password login, 45 durable ratings, protected exports, restart and backup',async t=>{
 const f=await fixture(t);
 assert.equal((await f.call('/api/research/summary')).status,401);
 assert.equal((await f.call('/api/research/summary',{headers:{'oai-authenticated-user-id':'forged','oai-authenticated-user-email':'researcher@example.test'}})).status,401);
 const login=await f.call('/api/auth/login',{method:'POST',data:{password}});assert.equal(login.status,200);const cookie=login.headers.get('set-cookie');assert.match(cookie,/HttpOnly/);assert.match(cookie,/SameSite=Strict/);const headers={Cookie:cookie.split(';')[0]};
 let summary=await (await f.call('/api/research/summary',{headers})).json();assert.deepEqual(summary.groups,[]);
 const token=crypto.randomUUID().replaceAll('-','')+crypto.randomUUID().replaceAll('-','');const auth={Authorization:`Bearer ${token}`};
 const s={nickname:'technical_demo',rating_scale:'va-0.01_match-0.5_naturalness-1_v2',participant_id:'TEST-'+crypto.randomUUID().replaceAll('-','').toUpperCase(),study_version:manifest.study_version,collection_version:COLLECTION_VERSION,record_type:'technical_test',group:3,seed:123,eligibility:{comfortable_english:true,headphones:true,previously_used_studio:false},consent:true,consent_utc:new Date().toISOString()};
 assert.equal((await f.call('/api/study/sessions',{method:'POST',data:s,headers:auth})).status,200);
 const rows=makeTrials(manifest,s.group,s.seed).map((item,i)=>({order:i+1,item_id:item.item_id,block_id:item.block_id,valence:.1,arousal:-.2,naturalness:3,target_match:4,play_count:1,completed_audio:true,elapsed_s:5,created_utc:new Date().toISOString()}));
 const path=`/api/study/sessions/${s.participant_id}/responses`;
 for(let i=0;i<2;i++)assert.equal((await f.call(path,{method:'POST',data:{rows},headers:auth})).status,200);
 assert.equal((await (await f.call('/api/research/responses.csv?type=technical',{headers})).text()).trim().split('\n').length,46);
 assert.equal((await (await f.call('/api/research/responses.csv',{headers})).text()).trim().split('\n').length,1);
 const backup=join(f.root,'backup.sqlite');execFileSync(process.execPath,['scripts/backup.mjs',backup],{env:{...process.env,ECHO_DATA_DIR:f.dataDir}});
 const backed=new DatabaseSync(backup);assert.equal(backed.prepare('SELECT count(*) AS n FROM study_responses').get().n,45);backed.close();
 await f.stop();await f.start();assert.equal((await f.call('/api/research/summary',{headers})).status,401);
 const saved=await (await f.call(`/api/study/sessions/${s.participant_id}`,{headers:auth})).json();assert.equal(saved.saved_count,45);
 const again=await f.call('/api/auth/login',{method:'POST',data:{password}});const refreshed={Cookie:again.headers.get('set-cookie').split(';')[0]};assert.equal((await f.call('/api/auth/logout',{method:'POST',headers:refreshed})).status,200);assert.equal((await f.call('/api/research/summary',{headers:refreshed})).status,401);
});
test('standalone exposes only public assets, safe ranges and explicit same-origin requests',async t=>{
 const f=await fixture(t);mkdirSync(join(f.publicDir,'models/qwen'),{recursive:true});writeFileSync(join(f.publicDir,'models/qwen/mlc-chat-config.json'),JSON.stringify({model_type:'qwen2'}));
 const localModel=await f.call(`/models/qwen/resolve/${QWEN_REVISION}/mlc-chat-config.json`);assert.equal(localModel.status,200);assert.deepEqual(await localModel.json(),{model_type:'qwen2'});
 const asset=await f.call('/sample.wav',{headers:{Range:'bytes=2-5'}});assert.equal(asset.status,206);assert.equal(await asset.text(),'2345');assert.equal(asset.headers.get('content-type'),'audio/wav');
 assert.equal((await f.call('/sample.wav',{headers:{Range:'bytes=50-'}})).status,416);
 for(const p of ['/data/researcher.json','/.env','/research-bundle/private/analysis-key.json','/server/auth.mjs'])assert.equal((await f.call(p)).status,404);
 try{symlinkSync(join(f.dataDir,'researcher.json'),join(f.publicDir,'leak.json'));assert.equal((await f.call('/leak.json')).status,404);}
 catch(error){if(error.code!=='EPERM')throw error;t.diagnostic('Symlink check skipped: Windows creates symlinks only with Developer Mode or administrator rights.');}
 assert.equal((await f.call('/api/auth/login',{method:'POST',data:{password},headers:{Origin:'https://foreign.example'}})).status,403);
 const forgedHost=await new Promise((resolve,reject)=>{const req=httpRequest(f.origin+'/',{headers:{Host:'foreign.example'}},res=>{res.resume();resolve(res.statusCode);});req.on('error',reject);req.end();});assert.equal(forgedHost,421);
 assert.equal((await f.call('/api/auth/login',{method:'POST',data:{password:'x'.repeat(3000)}})).status,413);
 assert.match((await f.call('/')).headers.get('content-security-policy'),/connect-src 'self' blob:/);
});
test('researcher passwords are hashed; expiry, rate limiting and reset revoke access',()=>{
 const dir=mkdtempSync(join(tmpdir(),'echo-auth-'));try{
  setPassword(dir,password);assert.doesNotMatch(readFileSync(join(dir,'researcher.json'),'utf8'),/correct-test-password/);assert.throws(()=>setPassword(dir,password),/already exists/);
  let time=1000;const auth=createAuth(dir,{clock:()=>time,secure:true});for(let i=0;i<5;i++)assert.equal(auth.login('wrong','ip').status,401);assert.equal(auth.login(password,'ip').status,429);time+=15*60*1000;
  const result=auth.login(password,'ip');assert.equal(result.status,200);assert.match(result.cookie,/Secure/);const req=new Request('https://study.example',{headers:{Cookie:result.cookie}});assert.equal(auth.authorised(req),true);time+=8*60*60*1000;assert.equal(auth.authorised(req),false);
  const next=auth.login(password,'ip');const nextReq=new Request('https://study.example',{headers:{Cookie:next.cookie}});setPassword(dir,'replacement-password-12345',{replace:true});assert.equal(auth.authorised(nextReq),false);assert.equal(auth.login(password,'ip').status,401);
 }finally{rmSync(dir,{recursive:true,force:true});}
});
