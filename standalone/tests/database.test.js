import previousManifest from '../public/study/manifest-v4.json' with {type:'json'};
import test from 'node:test';
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {mkdtempSync,rmSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import manifest from '../public/study/manifest.json' with {type:'json'};
import worker,{COLLECTION_VERSION} from '../server/worker.js';
import {localDatabase} from '../server/local-db.js';
import {makeTrials} from '../study-session.js';
import {StudySync,newSessionToken,wireRows} from '../study-sync.js';

const origin='https://study.example';
function fixture(t,filename=':memory:',assigned=manifest) {
 const DB=localDatabase(filename);t.after(()=>DB.close());
 const env={DB,RESEARCHER_AUTHORIZED:false};
 const s={nickname:'technical_demo',rating_scale:'va-0.01_match-0.5_naturalness-1_v2',participant_id:'TEST-'+crypto.randomUUID().replaceAll('-','').toUpperCase(),study_version:assigned.study_version,collection_version:COLLECTION_VERSION,record_type:'technical_test',group:0,seed:123,eligibility:{comfortable_english:false,headphones:false,previously_used_studio:false},consent:true,consent_utc:new Date().toISOString(),rows:[],remote:{token:newSessionToken(),consent_utc:new Date().toISOString(),saved_count:0}};
 const call=async(path,method='GET',data,headers={})=>worker.fetch(new Request(origin+path,{method,headers:{Origin:origin,'Content-Type':'application/json',Authorization:`Bearer ${s.remote.token}`,...headers},body:data?JSON.stringify(data):undefined}),env,{});
 const register=()=>call('/api/study/sessions','POST',s);
 const trials=makeTrials(assigned,s.group,s.seed);
 const row=(index,overrides={})=>({order:index+1,item_id:trials[index].item_id,block_id:trials[index].block_id,valence:.1,arousal:-.2,naturalness:3,target_match:4,play_count:1,completed_audio:true,elapsed_s:5.25,created_utc:new Date().toISOString(),...overrides});
 const save=rows=>call(`/api/study/sessions/${s.participant_id}/responses`,'POST',{rows});
 return {DB,env,s,call,register,trials,row,save};
}
test('database writes survive closing and reopening the local SQLite file',async t=>{
 const dir=mkdtempSync(join(tmpdir(),'echo-db-'));const f=fixture(t,join(dir,'study.sqlite'));t.after(()=>rmSync(dir,{recursive:true,force:true}));
 assert.equal((await f.register()).status,200);assert.equal((await f.save([f.row(0)])).status,200);
 const other=localDatabase(join(dir,'study.sqlite'));try{assert.equal((await other.prepare('SELECT COUNT(*) AS n FROM study_responses').first()).n,1);}finally{other.close();}
});
test('full 45-response session is idempotent and exports only in its correct cohort',async t=>{
 const f=fixture(t);assert.equal((await f.register()).status,200);
 const rows=Array.from({length:45},(_,i)=>f.row(i));
 assert.equal((await f.save(rows)).status,200);assert.equal((await f.save(rows)).status,200);
 const saved=await (await f.call(`/api/study/sessions/${f.s.participant_id}`)).json();assert.equal(saved.saved_count,45);assert.equal(saved.complete,true);
 assert.equal((await f.DB.prepare('SELECT COUNT(*) AS n FROM study_responses').first()).n,45);
 f.env.RESEARCHER_AUTHORIZED=true; const headers={};
 const human=await (await f.call('/api/research/responses.csv','GET',null,headers)).text();assert.equal(human.trim().split('\n').length,1);
 const technical=await (await f.call('/api/research/responses.csv?type=technical','GET',null,headers)).text();assert.equal(technical.trim().split('\n').length,46);assert.match(technical,/technical_test/);assert.doesNotMatch(technical,/token|consent_utc/);
 const summary=await (await f.call('/api/research/summary','GET',null,headers)).json();assert.equal(summary.groups[0].completed,1);assert.equal(summary.groups[0].responses,45);
});
test('initial perception remains locked after disclosure and concurrent conflicting requests',async t=>{
 const f=fixture(t);await f.register();const initial=f.row(0,{target_match:null});
 assert.equal((await f.save([initial])).status,200);
 let saved=await (await f.call(`/api/study/sessions/${f.s.participant_id}`)).json();assert.equal(saved.saved_count,0);assert.equal(saved.pending.valence,.1);
 assert.equal((await f.save([{...initial,valence:.8,target_match:4}])).status,409);
 const final={...initial,target_match:4};assert.equal((await f.save([final])).status,200);
 assert.equal((await f.save([{...final,target_match:1}])).status,409);
 const results=await Promise.all([f.save([f.row(1,{valence:.1})]),f.save([f.row(1,{valence:.6})])]);assert.ok(results.some(r=>r.status===409));
 saved=await (await f.call(`/api/study/sessions/${f.s.participant_id}`)).json();assert.equal(saved.rows[0].valence,.1);assert.equal(saved.rows[0].target_match,4);
});
test('server rejects forged allocation, missing consent, invalid scales and skipped clips',async t=>{
 const f=fixture(t);assert.equal((await f.call('/api/study/sessions','POST',{...f.s,consent:false})).status,400);await f.register();
 assert.equal((await f.call('/api/study/sessions','POST',{...f.s,group:3})).status,409);
 for(const row of [f.row(0,{item_id:'madeup'}),f.row(1),f.row(0,{valence:.123}),f.row(0,{target_match:0}),f.row(0,{elapsed_s:-1})]) assert.equal((await f.save([row])).status,400);
 assert.equal((await f.DB.prepare('SELECT COUNT(*) AS n FROM study_responses').first()).n,0);
});
test('human sessions require eligibility and completed playback; technical test identifiers cannot become human',async t=>{
 const f=fixture(t);f.s.participant_id=f.s.participant_id.replace('TEST-','P-');f.s.record_type='human_response';
 assert.equal((await f.register()).status,400);f.s.eligibility.comfortable_english=true;f.s.eligibility.headphones=true;
 assert.equal((await f.register()).status,200);assert.equal((await f.save([f.row(0,{play_count:0,completed_audio:false})])).status,400);
 assert.equal((await f.save([f.row(0)])).status,200);
});
test('session credentials and researcher identity protect reads and cross-origin writes',async t=>{
 const f=fixture(t);await f.register();
 assert.equal((await f.call(`/api/study/sessions/${f.s.participant_id}`,'GET',null,{Authorization:`Bearer ${newSessionToken()}`})).status,403);
 assert.equal((await f.call('/api/research/summary')).status,401);
 assert.equal((await f.call('/api/research/responses.csv','GET',null,{'oai-authenticated-user-id':'someone','oai-authenticated-user-email':'someone@example.com'})).status,401);
 assert.equal((await f.call('/api/study/sessions','POST',f.s,{Origin:'https://unrelated.example'})).status,403);
 assert.equal((await f.call('/api/study/sessions','POST',f.s,{'Content-Type':'text/plain'})).status,415);
 assert.equal((await f.call('/api/study/sessions','POST',{...f.s,padding:'x'.repeat(70000)})).status,413);
});
test('withdrawal removes ratings and prevents a delayed retry from restoring them',async t=>{
 const f=fixture(t);await f.register();const row=f.row(0);await f.save([row]);
 assert.equal((await f.call(`/api/study/sessions/${f.s.participant_id}`,'DELETE')).status,200);
 assert.equal((await f.call(`/api/study/sessions/${f.s.participant_id}`,'DELETE')).status,200);
 assert.equal((await f.save([row])).status,410);assert.equal((await f.register()).status,410);
 assert.equal((await f.DB.prepare('SELECT COUNT(*) AS n FROM study_responses').first()).n,0);
});
test('browser queue retries after a lost server acknowledgement without duplicate rows',async t=>{
 const f=fixture(t);let drop=true;const states=[];
 const fetcher=async(path,options)=>{const response=await f.call(path,options.method,options.body?JSON.parse(options.body):null,options.headers);if(path.endsWith('/responses')&&drop){drop=false;throw new Error('Connection interrupted after commit');}return response;};
 const client=new StudySync({session:f.s,trials:f.trials,fetcher,onStatus:s=>states.push(s)});
 f.s.rows=[f.row(0)];await client.sync();assert.equal(states.at(-1).state,'offline');assert.equal((await f.DB.prepare('SELECT COUNT(*) AS n FROM study_responses').first()).n,1);
 await client.sync();assert.equal(states.at(-1).state,'saved');assert.equal(states.at(-1).saved,1);assert.equal((await f.DB.prepare('SELECT COUNT(*) AS n FROM study_responses').first()).n,1);
});
test('resuming recovers the server-confirmed perception lock and final rows',async t=>{
 const f=fixture(t);await f.register();await f.save([f.row(0),f.row(1,{target_match:null})]);
 const fetcher=(path,options)=>f.call(path,options.method,options.body?JSON.parse(options.body):null,options.headers);
 const client=new StudySync({session:f.s,trials:f.trials,fetcher});await client.restore();assert.equal(f.s.rows.length,1);assert.equal(f.s.current.index,1);assert.equal(f.s.current.locked.valence,.1);
 assert.equal(wireRows(f.s,f.trials)[1].target_match,null);
});

test('previous 27-clip sessions resume and complete without changing their allocation or hashes; no new one starts',async t=>{
 const f=fixture(t,':memory:',previousManifest);assert.equal((await f.register()).status,409);assert.equal((await f.DB.prepare('SELECT COUNT(*) AS n FROM study_sessions').first()).n,0);
 await f.DB.prepare('INSERT INTO study_sessions (participant_id,token_hash,study_version,collection_version,record_type,group_number,seed,comfortable_english,headphones,previously_used_studio,consent_utc,received_utc,updated_utc,nickname,rating_scale) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)').bind(f.s.participant_id,createHash('sha256').update(f.s.remote.token).digest('hex'),f.s.study_version,f.s.collection_version,f.s.record_type,f.s.group+1,f.s.seed,0,0,0,f.s.consent_utc,f.s.consent_utc,f.s.consent_utc,f.s.nickname,f.s.rating_scale).run();
 assert.equal((await f.register()).status,200);
 const rows=Array.from({length:27},(_,i)=>f.row(i));assert.equal((await f.save(rows.slice(0,12))).status,200);
 const pending=await (await f.call(`/api/study/sessions/${f.s.participant_id}`)).json();assert.equal(pending.saved_count,12);assert.equal(pending.complete,false);assert.equal(pending.trials_per_session,27);
 assert.equal((await f.register()).status,200);assert.equal((await f.save(rows)).status,200);
 const saved=await (await f.call(`/api/study/sessions/${f.s.participant_id}`)).json();assert.equal(saved.complete,true);assert.equal(saved.saved_count,27);assert.equal(saved.study_version,previousManifest.study_version);
 assert.ok(saved.rows.every(r=>previousManifest.items.find(i=>i.item_id===r.item_id)?.sha256===r.audio_sha256));
 assert.equal((await f.save([f.row(0,{order:28})])).status,400);
 f.env.RESEARCHER_AUTHORIZED=true;const headers={};
 const summary=await (await f.call('/api/research/summary','GET',null,headers)).json();assert.equal(summary.groups.length,0);assert.equal(summary.sessions[0].trials_per_session,27);
});
