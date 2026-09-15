import test from 'node:test';
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {readFileSync} from 'node:fs';
import manifest from '../public/study/manifest.json' with {type:'json'};
import worker,{COLLECTION_VERSION} from '../server/worker.js';
import {localDatabase} from '../server/local-db.js';
import {newSessionToken} from '../study-sync.js';
import {RATING_SCALE} from '../study-session.js';
import {createInteractiveSession} from '../interactive-sync.js';
import {LISTENING_ID_PREFIX,CONVERSATION_ID_PREFIX} from '../study-cohort.js';

const origin='https://study.example',L='L-'+'A'.repeat(32);
const read=path=>readFileSync(new URL('../'+path,import.meta.url),'utf8');
const hex=()=>crypto.randomUUID().replaceAll('-','').toUpperCase();
function setup(t){
 const DB=localDatabase(':memory:');t.after(()=>DB.close());const env={DB,RESEARCHER_AUTHORIZED:false};
 const call=(path,data,token)=>worker.fetch(new Request(origin+path,{method:'POST',headers:{Origin:origin,'Content-Type':'application/json',Authorization:`Bearer ${token}`},body:JSON.stringify(data)}),env,{});
 const listening=(participant_id,extra={})=>({participant_id,nickname:'cohort_check',listener_id:L,rating_scale:RATING_SCALE,study_version:manifest.study_version,collection_version:COLLECTION_VERSION,record_type:'human_response',group:0,seed:1,eligibility:{comfortable_english:true,headphones:true,previously_used_studio:false},consent:true,consent_utc:new Date().toISOString(),gender:'na',...extra});
 return {DB,call,listening};
}

test('new official sessions use EXP1 codes; an out-of-date page cannot start a P- or X- session', async t=>{
 const f=setup(t);
 assert.equal((await f.call('/api/study/sessions',f.listening(LISTENING_ID_PREFIX+hex()),newSessionToken())).status,200);
 const stale=await f.call('/api/study/sessions',f.listening('P-'+hex()),newSessionToken());
 assert.equal(stale.status,409);assert.match((await stale.json()).error,/out of date/);
 const technical=f.listening('TEST-'+hex(),{record_type:'technical_test',eligibility:{comfortable_english:false,headphones:false,previously_used_studio:false}});
 assert.equal((await f.call('/api/study/sessions',technical,newSessionToken())).status,200);
 const session=createInteractiveSession('line','cohort_check',null,'na');
 assert.ok(session.session_id.startsWith(CONVERSATION_ID_PREFIX));
 const {token,turns,saved_count,...meta}=session;
 assert.equal((await f.call('/api/interactive/sessions',{...meta,listener_id:L},token)).status,200);
 assert.equal((await f.call('/api/interactive/sessions',{...meta,listener_id:L,session_id:'X-'+hex()},newSessionToken())).status,409);
 assert.equal((await f.call('/api/interactive/sessions',{...meta,listener_id:L,session_id:'X-'+hex(),record_type:'technical_test'},newSessionToken())).status,200);
});

test('an unfinished P- session started before the cut-off can still be resumed', async t=>{
 const f=setup(t),token=newSessionToken(),hash=createHash('sha256').update(token).digest('hex'),pid='P-'+hex(),now=new Date().toISOString(),s=f.listening(pid);
 await f.DB.prepare('INSERT INTO study_sessions (participant_id,token_hash,study_version,collection_version,record_type,group_number,seed,comfortable_english,headphones,previously_used_studio,consent_utc,received_utc,updated_utc,nickname,rating_scale,listener_id) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)')
  .bind(pid,hash,s.study_version,COLLECTION_VERSION,'human_response',1,1,1,1,0,s.consent_utc,now,now,'cohort_check',RATING_SCALE,L).run();
 assert.equal((await f.call('/api/study/sessions',s,token)).status,200);
});

test('the pages create EXP1 codes for official sessions', ()=>{
 assert.match(read('listen.js'),/participant_id:\(test\?'TEST-':LISTENING_ID_PREFIX\)/);
 assert.match(read('interactive-sync.js'),/session_id:\(technical\?'X-':CONVERSATION_ID_PREFIX\)/);
});
