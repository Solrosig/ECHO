import test from 'node:test';
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {readFileSync,readdirSync} from 'node:fs';
import manifest from '../public/study/manifest.json' with {type:'json'};
import worker,{COLLECTION_VERSION} from '../server/worker.js';
import {localDatabase} from '../server/local-db.js';
import {newSessionToken} from '../study-sync.js';
import {RATING_SCALE} from '../study-session.js';
import {createInteractiveSession} from '../interactive-sync.js';
import {validateGender,GENDERS} from '../participant.js';
import {LISTENING_ID_PREFIX} from '../study-cohort.js';

// The author, 2026-09-15: "add line Gender with 3 check boxes Female, Male, N/A. Gender fill is to be required".
const origin='https://study.example',L='L-'+'D'.repeat(32);
const read=path=>readFileSync(new URL('../'+path,import.meta.url),'utf8');
const hex=()=>crypto.randomUUID().replaceAll('-','').toUpperCase();
const MARK='<span class="required-mark" aria-hidden="true">*</span>';
const FIELD='<fieldset class="gender-field"><legend>Gender'+MARK+'</legend><label><input type="radio" name="gender" value="female" required> Female</label><label><input type="radio" name="gender" value="male" required> Male</label><label><input type="radio" name="gender" value="na" required> N/A</label></fieldset>';
function setup(t){
 const DB=localDatabase(':memory:');t.after(()=>DB.close());const env={DB,RESEARCHER_AUTHORIZED:false};
 const call=(path,data,token,method='POST')=>worker.fetch(new Request(origin+path,{method,headers:{Origin:origin,'Content-Type':'application/json',Authorization:`Bearer ${token}`},body:data===undefined?undefined:JSON.stringify(data)}),env,{});
 const research=async path=>(await worker.fetch(new Request(origin+path),env,{}));
 const listening=(extra={})=>({participant_id:LISTENING_ID_PREFIX+hex(),nickname:'gender_check',listener_id:L,rating_scale:RATING_SCALE,study_version:manifest.study_version,collection_version:COLLECTION_VERSION,record_type:'human_response',group:0,seed:1,eligibility:{comfortable_english:true,headphones:true,previously_used_studio:false},consent:true,consent_utc:new Date().toISOString(),...extra});
 const conversation=gender=>{const {token,turns,saved_count,...metadata}=createInteractiveSession('line','gender_check',null,gender);return {metadata:{...metadata,listener_id:L},token};};
 const stored=async(table,key,id)=>(await DB.prepare(`SELECT gender FROM ${table} WHERE ${key}=?`).bind(id).first())?.gender;
 return {DB,env,call,research,listening,conversation,stored};
}

test('every entry form asks for gender after the nickname, as one required choice of Female, Male or N/A',()=>{
 for(const [page,nickname] of [['index.html','id="entry-nickname"'],['listen.html','id="study-nickname"'],['studio.html','id="nickname"']]){
  const html=read(page);
  assert.ok(html.includes(FIELD),page);
  assert.equal(html.split('<fieldset class="gender-field">').length-1,1,page);
  assert.ok(html.indexOf(nickname)<html.indexOf(FIELD),page);
 }
 assert.deepEqual(Object.entries(GENDERS),[['female','Female'],['male','Male'],['na','N/A']]);
 for(const value of ['female','male','na'])assert.equal(validateGender(value),value);
 for(const value of ['','Female','other',null,undefined,1])assert.throws(()=>validateGender(value),/Choose your gender/);
 assert.match(read('style.css'),/\.gender-field\{border:0;/);
 assert.match(read('home.css'),/\.entry-form \.required-mark\{color:#c62828;/);
});

test('the pages require the choice, remember it like the nickname and send it with each new session',()=>{
 assert.match(read('home.js'),/rememberGender\(form\.elements\.gender\.value\)/);
 assert.match(read('app.js'),/gender:rememberGender\(\$\('identity-form'\)\.elements\.gender\.value\)/);
 assert.match(read('app.js'),/createInteractiveSession\('explore',nickname,\$\('chat-engine'\)\.value,gender\)/);
 assert.match(read('listen.js'),/gender:test&&!gender\?null:rememberGender\(gender\)/);
 assert.match(read('study-sync.js'),/gender:s\.gender\?\?null\}/);
 assert.equal(createInteractiveSession('explore','gender_check','kokoro','na').gender,'na');
 assert.equal(createInteractiveSession('line','gender_check',null).gender,null);
 assert.throws(()=>createInteractiveSession('line','gender_check',null,'x'),/Choose your gender/);
});

test('a new Listening session needs a gender; technical tests may omit it; withdrawal clears it',async t=>{
 const f=setup(t);
 const saved=f.listening({gender:'female'}),token=newSessionToken();
 assert.equal((await f.call('/api/study/sessions',saved,token)).status,200);
 assert.equal(await f.stored('study_sessions','participant_id',saved.participant_id),'female');
 const stale=await f.call('/api/study/sessions',f.listening(),newSessionToken());
 assert.equal(stale.status,409);assert.match((await stale.json()).error,/out of date/);
 assert.equal((await f.call('/api/study/sessions',f.listening({gender:'other'}),newSessionToken())).status,400);
 const technical=f.listening({participant_id:'TEST-'+hex(),record_type:'technical_test',eligibility:{comfortable_english:false,headphones:false,previously_used_studio:false}});
 assert.equal((await f.call('/api/study/sessions',technical,newSessionToken())).status,200);
 assert.equal(await f.stored('study_sessions','participant_id',technical.participant_id),null);
 // The browser copy registers again on every resume; one without a gender field still resumes.
 const {gender,...withoutGender}=saved;
 assert.equal((await f.call('/api/study/sessions',withoutGender,token)).status,200);
 assert.equal(await f.stored('study_sessions','participant_id',saved.participant_id),'female');
 assert.equal((await f.call(`/api/study/sessions/${saved.participant_id}`,undefined,token,'DELETE')).status,200);
 assert.equal(await f.stored('study_sessions','participant_id',saved.participant_id),null);
});

test('a session stored before gender was asked takes the first gender its browser sends and keeps it',async t=>{
 const f=setup(t),token=newSessionToken(),hash=createHash('sha256').update(token).digest('hex'),s=f.listening({gender:'male'}),now=new Date().toISOString();
 await f.DB.prepare('INSERT INTO study_sessions (participant_id,token_hash,study_version,collection_version,record_type,group_number,seed,comfortable_english,headphones,previously_used_studio,consent_utc,received_utc,updated_utc,nickname,rating_scale,listener_id) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)')
  .bind(s.participant_id,hash,s.study_version,COLLECTION_VERSION,'human_response',1,1,1,1,0,s.consent_utc,now,now,s.nickname,RATING_SCALE,L).run();
 assert.equal(await f.stored('study_sessions','participant_id',s.participant_id),null);
 assert.equal((await f.call('/api/study/sessions',s,token)).status,200);
 assert.equal(await f.stored('study_sessions','participant_id',s.participant_id),'male');
 assert.equal((await f.call('/api/study/sessions',{...s,gender:'female'},token)).status,200);
 assert.equal(await f.stored('study_sessions','participant_id',s.participant_id),'male');
});

test('a new Test Mode or Explore session needs a gender; technical sessions may omit it; withdrawal clears it',async t=>{
 const f=setup(t);
 const chosen=f.conversation('na');
 assert.equal((await f.call('/api/interactive/sessions',chosen.metadata,chosen.token)).status,200);
 assert.equal(await f.stored('interactive_sessions','session_id',chosen.metadata.session_id),'na');
 const missing=f.conversation(null);
 const stale=await f.call('/api/interactive/sessions',missing.metadata,missing.token);
 assert.equal(stale.status,409);assert.match((await stale.json()).error,/out of date/);
 assert.equal((await f.call('/api/interactive/sessions',{...missing.metadata,gender:'unknown'},missing.token)).status,400);
 const technical={...missing.metadata,session_id:'X-'+hex(),record_type:'technical_test'};
 assert.equal((await f.call('/api/interactive/sessions',technical,missing.token)).status,200);
 assert.equal(await f.stored('interactive_sessions','session_id',technical.session_id),null);
 assert.equal((await f.call(`/api/interactive/sessions/${chosen.metadata.session_id}`,undefined,chosen.token,'DELETE')).status,200);
 assert.equal(await f.stored('interactive_sessions','session_id',chosen.metadata.session_id),null);
});

test('migration 0009 adds an optional gender column to both session tables, and researchers see it',async t=>{
 const f=setup(t);
 assert.ok(readdirSync(new URL('../drizzle/',import.meta.url)).includes('0009_participant_gender.sql'));
 for(const table of ['study_sessions','interactive_sessions']){
  const column=(await f.DB.prepare(`PRAGMA table_info(${table})`).all()).results.find(c=>c.name==='gender');
  assert.ok(column,table);assert.equal(column.notnull,0,table);
 }
 const saved=f.listening({gender:'female'});assert.equal((await f.call('/api/study/sessions',saved,newSessionToken())).status,200);
 const chat=f.conversation('male');assert.equal((await f.call('/api/interactive/sessions',chat.metadata,chat.token)).status,200);
 f.env.RESEARCHER_AUTHORIZED=true;
 const summary=await (await f.research('/api/research/summary')).json();
 assert.equal(summary.sessions.find(s=>s.participant_id===saved.participant_id).gender,'female');
 const interactive=await (await f.research('/api/research/interactive')).json();
 assert.equal(interactive.sessions.find(s=>s.session_id===chat.metadata.session_id).gender,'male');
 // The response CSV that the frozen analysis reads keeps its columns.
 assert.doesNotMatch((await (await f.research('/api/research/responses.csv')).text()).split('\r\n')[0],/gender/);
 assert.ok(read('research.html').includes('<th>Nickname</th><th>Gender</th><th>Participant code</th>'));
 assert.ok(read('research.html').includes('<th>Nickname</th><th>Gender</th><th>Mode</th>'));
 assert.match(read('scripts/export-listeners.mjs'),/nickname:s\.nickname,gender:s\.gender\?\?null,session_id:s\.participant_id/);
});
