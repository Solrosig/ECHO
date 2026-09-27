import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync,readFileSync,rmSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {DatabaseSync} from 'node:sqlite';
import worker,{COLLECTION_VERSION} from '../server/worker.js';
import {localDatabase} from '../server/local-db.js';
import {controlsFor,ENGINES} from '../voice-controls.js';
import {EXPLORE_ENGINES,EXPLORE_NAMES} from '../engine-catalog.js';
import {validateNickname} from '../participant.js';
import {createInteractiveSession,InteractiveSync} from '../interactive-sync.js';
import {newSessionToken} from '../study-sync.js';
import {makeTrials,RATING_SCALE} from '../study-session.js';
import manifest from '../public/study/manifest.json' with {type:'json'};
const origin='https://echo.example';
function fixture(t,mode='explore',engine='chatterbox'){
 const DB=localDatabase();t.after(()=>DB.close());const env={DB,RESEARCHER_AUTHORIZED:true,RESEARCHER_EMAIL:'reviewer@example.test'};
 const s=createInteractiveSession(mode,'technical_tester',mode==='line'?null:engine);s.record_type='technical_test';
 const call=async(path,method='GET',data,headers={})=>worker.fetch(new Request(origin+path,{method,headers:{Origin:origin,'Content-Type':'application/json',Authorization:`Bearer ${s.token}`,'oai-authenticated-user-id':'reviewer','oai-authenticated-user-email':'reviewer@example.test',...headers},body:data?JSON.stringify(data):undefined}),env,{});
 const register=()=>call('/api/interactive/sessions','POST',s),save=turns=>call(`/api/interactive/sessions/${s.session_id}/turns`,'POST',{turns});
 const turn=(order=1,overrides={})=>({order,engine,emotion:'happy',input_text:'Hello from the technical fixture.',output_text:mode==='line'?'Hello from the technical fixture.':'Hello. This is a technical fixture.',controls:controlsFor({engine,emotion:'happy'}),audio_sha256:'a'.repeat(64),duration_s:2.5,elapsed_s:.8,created_utc:'2026-09-07T12:00:00.000Z',...overrides});
 return {DB,env,s,call,register,save,turn};
}
test('Explore stores exactly ten exchanges, locks its engine and nickname, and prevents an eleventh',async t=>{
 const f=fixture(t);assert.equal((await f.register()).status,200);
 assert.equal((await f.call('/api/interactive/sessions','POST',{...f.s,engine:'kokoro'})).status,409);
 assert.equal((await f.call('/api/interactive/sessions','POST',{...f.s,nickname:'someone_else'})).status,409);
 assert.equal((await f.save([f.turn(1,{engine:'kokoro',controls:controlsFor({engine:'kokoro',emotion:'happy'})})])).status,400);
 const turns=Array.from({length:10},(_,i)=>f.turn(i+1));assert.equal((await f.save(turns)).status,200);assert.equal((await f.save(turns)).status,200);
 assert.equal((await f.save([f.turn(11)])).status,400);
 assert.equal((await f.save([f.turn(1,{output_text:'A conflicting reply.'})])).status,409);
 const saved=await (await f.call(`/api/interactive/sessions/${f.s.session_id}`)).json();assert.equal(saved.saved_count,10);assert.equal(saved.nickname,'technical_tester');assert.equal(saved.turns[0].output_text,turns[0].output_text);
 const csv=await (await f.call('/api/research/interactive.csv')).text();assert.equal(csv.trim().split('\n').length,11);assert.match(csv,/technical_tester/);assert.match(csv,/technical_test/);assert.doesNotMatch(csv,/token/);
 assert.equal((await (await f.call('/api/research/responses.csv')).text()).trim().split('\n').length,1);
});
test('Explore offers exactly the report shortlist, CosyVoice 2 by its plain name, and stores its conversation; Test mode keeps its pinned name',async t=>{
 assert.deepEqual([...EXPLORE_ENGINES].sort(),['chatterbox','cosyvoice2','kokoro']);assert.equal(EXPLORE_NAMES.cosyvoice2,'CosyVoice 2');assert.equal(ENGINES.cosyvoice2.name,'CosyVoice2');
 const studio=readFileSync(new URL('../studio.html',import.meta.url),'utf8');
 assert.equal(studio.match(/<select id="chat-engine">.*?<\/select>/)[0],'<select id="chat-engine"><option value="chatterbox">Chatterbox</option><option value="kokoro">Kokoro</option><option value="cosyvoice2">CosyVoice 2</option></select>');
 const parler=fixture(t,'explore','parlertts');assert.equal((await parler.register()).status,400);
 assert.match(readFileSync(new URL('../app.js',import.meta.url),'utf8'),/\['chat-engine',EXPLORE_ENGINES,exploreName\]/);
 const f=fixture(t,'explore','cosyvoice2');assert.equal((await f.register()).status,200);
 assert.equal((await f.save([f.turn(1),f.turn(2)])).status,200);
 const saved=await (await f.call(`/api/interactive/sessions/${f.s.session_id}`)).json();assert.equal(saved.saved_count,2);
 assert.match(await (await f.call('/api/research/interactive.csv')).text(),/cosyvoice2/);
});
test('Voice a line accepts all existing engines and custom controls, and rejects altered output text',async t=>{
 const f=fixture(t,'line');await f.register();
 const turns=['chatterbox','kokoro','styletts2','cosyvoice2','parlertts'].map((engine,i)=>f.turn(i+1,{engine,controls:controlsFor({engine,emotion:'happy'})}));
 assert.equal((await f.save(turns)).status,200);
 assert.equal((await f.save([f.turn(6,{output_text:'This is not the original line.'})])).status,400);
 const controls=controlsFor({engine:'kokoro',emotion:'happy',condition:'custom',custom:{rate:1.04,gain:.8,pitch:1.25}});assert.equal((await f.save([f.turn(6,{engine:"kokoro",controls})])).status,200);
});
test('Interactive sessions require consent, original credentials, sequential writes and private research access',async t=>{
 const f=fixture(t);assert.equal((await f.call('/api/interactive/sessions','POST',{...f.s,consent:false})).status,400);await f.register();
 assert.equal((await f.call(`/api/interactive/sessions/${f.s.session_id}`,'GET',null,{Authorization:`Bearer ${newSessionToken()}`})).status,403);
 assert.equal((await f.save([f.turn(2)])).status,400);assert.equal((await f.save([f.turn()])).status,200);
 f.env.RESEARCHER_AUTHORIZED=false;
 assert.equal((await f.call('/api/research/interactive','GET',null,{'oai-authenticated-user-id':'','oai-authenticated-user-email':''})).status,401);
 assert.equal((await f.call(`/api/interactive/sessions/${f.s.session_id}`,'DELETE')).status,200);assert.equal((await f.save([f.turn()])).status,410);assert.equal((await f.register()).status,410);
 assert.equal((await f.DB.prepare('SELECT COUNT(*) AS n FROM interactive_turns').first()).n,0);
});
test('Interactive retry after a lost acknowledgement stores one record, with no duplicate exchange',async t=>{
 const f=fixture(t);let drop=true;const states=[];
 const fetcher=async(path,opts)=>{const response=await f.call(path,opts.method,JSON.parse(opts.body),opts.headers);if(path.endsWith('/turns')&&drop){drop=false;throw new Error('Lost acknowledgement');}return response;};
 const sync=new InteractiveSync(f.s,{fetcher,onStatus:s=>states.push(s)});await sync.add(f.turn());assert.equal(states.at(-1).state,'offline');await sync.sync();assert.equal(states.at(-1).state,'saved');assert.equal(f.s.saved_count,1);assert.equal((await f.DB.prepare('SELECT COUNT(*) AS n FROM interactive_turns').first()).n,1);
});
test('New listening scales persist half-step matches, fine valence, nickname and collection version',async t=>{
 const f=fixture(t),pid='TEST-'+crypto.randomUUID().replaceAll('-','').toUpperCase();const s={participant_id:pid,nickname:'fine_scale_tester',rating_scale:RATING_SCALE,study_version:manifest.study_version,collection_version:COLLECTION_VERSION,record_type:'technical_test',group:1,seed:42,consent:true,consent_utc:'2026-09-07T12:00:00Z',eligibility:{comfortable_english:true,headphones:true,previously_used_studio:false}};
 assert.equal((await f.call('/api/study/sessions','POST',s)).status,200);const trial=makeTrials(manifest,1,42)[0];const row={order:1,item_id:trial.item_id,block_id:trial.block_id,valence:.37,arousal:-.91,naturalness:4,target_match:3.5,play_count:1,completed_audio:true,elapsed_s:10,created_utc:'2026-09-07T12:00:00Z'};
 assert.equal((await f.call(`/api/study/sessions/${pid}/responses`,'POST',{rows:[row]})).status,200);
 const saved=await (await f.call(`/api/study/sessions/${pid}`)).json();assert.equal(saved.rows[0].target_match,3.5);assert.equal(saved.rows[0].valence,.37);assert.equal(saved.rows[0].nickname,'fine_scale_tester');assert.equal(saved.rows[0].rating_scale,RATING_SCALE);assert.equal(saved.rows[0].collection_version,COLLECTION_VERSION);
});
test('Migration keeps existing responses and marks their legacy scale',()=>{
 const dir=mkdtempSync(join(tmpdir(),'echo-v1-migration-')),file=join(dir,'study.sqlite');let db;
 try{const old=new DatabaseSync(file);old.exec(readFileSync(new URL('../drizzle/0000_cold_timeslip.sql',import.meta.url),'utf8'));old.exec("CREATE TABLE _local_migrations(name TEXT PRIMARY KEY); INSERT INTO _local_migrations VALUES ('0000_cold_timeslip.sql')");old.prepare('INSERT INTO study_sessions VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)').run('TEST-ABCD1234','hash','old-stimulus','old-collection','technical_test',1,42,1,1,0,'date','date','date',null,null);old.prepare('INSERT INTO study_responses VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)').run('TEST-ABCD1234',1,'item','block',.2,.3,4,3,1,1,10,'date','date','date');old.close();db=localDatabase(file);const s=db.sqlite.prepare('SELECT * FROM study_sessions').get(),response=db.sqlite.prepare('SELECT * FROM study_responses').get();assert.equal(s.nickname,'');assert.equal(s.rating_scale,'va-0.05_match-1_naturalness-1_v1');assert.equal(response.target_match,3);assert.equal(response.valence,.2);}finally{db?.close();rmSync(dir,{recursive:true,force:true});}
});
test('Nicknames allow Ukrainian aliases and reject email addresses or formula prefixes',()=>{assert.equal(validateNickname('  слухач_07  '),'слухач_07');for(const name of ['a','name@example.com','=IMPORTDATA','<script>','x'.repeat(33)])assert.throws(()=>validateNickname(name));});

test('Engine migration preserves existing eSpeak conversations and their child turns with foreign keys enforced',()=>{
 const db=new DatabaseSync(':memory:');try{
  db.exec('PRAGMA foreign_keys=ON');
  // Read the actual pre-replacement migrations, including their original identifiers.
  for(const name of ['0000_cold_timeslip.sql', '0001_medical_stryfe.sql', '0002_conscious_echo.sql'])db.exec(readFileSync(new URL('../drizzle/'+name,import.meta.url),'utf8'));
  db.prepare('INSERT INTO interactive_sessions VALUES (?,?,?,?,?,?,?,?,?,?,?)').run('X-LEGACY','hash','legacy_nick','explore','espeak','technical_test','old-version','date','date','date',null);
  db.prepare('INSERT INTO interactive_turns VALUES (?,?,?,?,?,?,?,?,?)').run('X-LEGACY',1,'espeak','happy','Earlier input','Earlier reply','{"legacy":true}','date','date');
  db.exec(readFileSync(new URL('../drizzle/0003_fearless_maggott.sql',import.meta.url),'utf8'));
  assert.equal(db.prepare('SELECT count(*) AS n FROM interactive_turns').get().n,1);assert.equal(db.prepare('SELECT engine FROM interactive_sessions').get().engine,'espeak');assert.equal(db.prepare('SELECT turn_json FROM interactive_turns').get().turn_json,'{"legacy":true}');
  assert.equal(db.prepare('PRAGMA foreign_keys').get().foreign_keys,1);assert.equal(db.prepare('PRAGMA foreign_key_check').all().length,0);
  db.prepare('INSERT INTO interactive_sessions VALUES (?,?,?,?,?,?,?,?,?,?,?)').run('X-NEW','hash','new_nick','explore','chatterbox','technical_test','new-version','date','date','date',null);
  db.prepare('INSERT INTO interactive_turns VALUES (?,?,?,?,?,?,?,?,?)').run('X-NEW',1,'chatterbox','happy','Input','Reply','{}','date','date');assert.equal(db.prepare('SELECT count(*) AS n FROM interactive_turns').get().n,2);
 }finally{db.close();}
});

test('Each generated message accepts one complete exploratory rating, exports it, and deletes it on withdrawal',async t=>{
 const f=fixture(t,'line');await f.register();await f.save([f.turn()]);
 const rating={valence:.37,arousal:-.42,naturalness:4,target_match:3.5,rating_scale:RATING_SCALE,version:'echo-message-rating-v1',completed_audio:true,play_count:1,elapsed_s:12,created_utc:'2026-09-07T20:00:00Z'};
 const path=`/api/interactive/sessions/${f.s.session_id}/ratings`,save=r=>f.call(path,'POST',{ratings:[{order:1,rating:r}]});
 assert.equal((await save({...rating,completed_audio:false})).status,400);
 assert.equal((await save({...rating,target_match:3.25})).status,400);
 assert.equal((await f.call(path,'POST',{ratings:[{order:2,rating}]})).status,400);
 assert.equal((await save(rating)).status,200);assert.equal((await save(rating)).status,200);
 assert.equal((await save({...rating,naturalness:1})).status,409);
 assert.equal((await f.call(path,'POST',{ratings:[{order:1,rating}]},{Authorization:`Bearer ${newSessionToken()}`})).status,403);
 const saved=await(await f.call(`/api/interactive/sessions/${f.s.session_id}`)).json();assert.equal(saved.ratings.length,1);assert.equal(saved.ratings[0].rating.target_match,3.5);
 const csv=await(await f.call('/api/research/interactive.csv')).text();assert.match(csv,/rating_status/);assert.match(csv,/"rated"/);assert.match(csv,/"0.37"/);assert.match(csv,/"3.5"/);
 assert.equal((await(await f.call('/api/research/responses.csv')).text()).trim().split('\n').length,1);
 await f.call(`/api/interactive/sessions/${f.s.session_id}`,'DELETE');assert.equal((await f.DB.prepare('SELECT COUNT(*) n FROM interactive_ratings').first()).n,0);assert.equal((await save(rating)).status,410);
});
test('Lost rating acknowledgement retries without duplicating ratings or messages',async t=>{
 const f=fixture(t);let drop=true;
 const fetcher=async(path,opts)=>{const response=await f.call(path,opts.method,JSON.parse(opts.body),opts.headers);if(path.endsWith('/ratings')&&drop){drop=false;throw new Error('Lost rating acknowledgement');}return response;};
 const sync=new InteractiveSync(f.s,{fetcher});await sync.add(f.turn());await sync.rate(1,{valence:0,arousal:0,naturalness:3,target_match:3,rating_scale:RATING_SCALE,version:'echo-message-rating-v1',completed_audio:true,play_count:1,elapsed_s:12,created_utc:'2026-09-07T20:00:00Z'});
 assert.equal(f.s.saved_rating_count,undefined);await sync.sync();assert.equal(f.s.saved_rating_count,1);assert.deepEqual(f.s.saved_rating_orders,[1]);assert.equal((await f.DB.prepare('SELECT COUNT(*) n FROM interactive_ratings').first()).n,1);assert.equal((await f.DB.prepare('SELECT COUNT(*) n FROM interactive_turns').first()).n,1);
});
