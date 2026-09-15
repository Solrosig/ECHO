import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import manifest from '../public/study/manifest.json' with {type:'json'};
import worker,{COLLECTION_VERSION} from '../server/worker.js';
import {localDatabase} from '../server/local-db.js';
import {newSessionToken} from '../study-sync.js';
import {RATING_SCALE} from '../study-session.js';
import {createInteractiveSession} from '../interactive-sync.js';
import {nicknameAvailable,NICKNAME_TAKEN} from '../participant.js';

const origin='https://study.example',A='L-'+'A'.repeat(32),B='L-'+'B'.repeat(32);
const read=path=>readFileSync(new URL('../'+path,import.meta.url),'utf8');
function setup(t){
 const DB=localDatabase(':memory:');t.after(()=>DB.close());const env={DB,RESEARCHER_AUTHORIZED:false};
 const call=(path,data,token=newSessionToken(),method='POST')=>worker.fetch(new Request(origin+path,{method,headers:{Origin:origin,'Content-Type':'application/json',Authorization:`Bearer ${token}`},body:data===undefined?undefined:JSON.stringify(data)}),env,{});
 const listening=(nickname,listener_id,extra={})=>({participant_id:'EXP1-'+crypto.randomUUID().replaceAll('-','').toUpperCase(),nickname,listener_id,rating_scale:RATING_SCALE,study_version:manifest.study_version,collection_version:COLLECTION_VERSION,record_type:'human_response',group:0,seed:1,eligibility:{comfortable_english:true,headphones:true,previously_used_studio:false},consent:true,consent_utc:new Date().toISOString(),gender:'female',...extra});
 const conversation=(nickname,listener_id)=>{const {token,turns,saved_count,...metadata}=createInteractiveSession('line',nickname,null,'female');return {metadata:{...metadata,listener_id},token};};
 const check=async(nickname,listener_id)=>(await call('/api/nicknames/check',{nickname,listener_id})).json();
 return {call,listening,conversation,check};
}

test('a nickname used by another browser is refused; the same browser keeps it across Listening, Test Mode and Explore',async t=>{
 const f=setup(t);
 assert.deepEqual(await f.check('anna_07',A),{available:true,message:null});
 const first=f.listening('anna_07',A),tokenA=newSessionToken();
 assert.equal((await f.call('/api/study/sessions',first,tokenA)).status,200);
 assert.equal((await f.check('anna_07',A)).available,true);
 assert.deepEqual(await f.check('ANNA_07',B),{available:false,message:NICKNAME_TAKEN});
 // The server refuses the duplicate even when a page skips the check.
 const refused=await f.call('/api/study/sessions',f.listening('anna_07',B));
 assert.equal(refused.status,409);assert.equal((await refused.json()).error,NICKNAME_TAKEN);
 const line=f.conversation('anna_07',B);
 assert.equal((await f.call('/api/interactive/sessions',line.metadata,line.token)).status,409);
 // Browser A continues: its Listening session registers again and Test Mode starts under the same nickname.
 assert.equal((await f.call('/api/study/sessions',first,tokenA)).status,200);
 const own=f.conversation('anna_07',A);
 assert.equal((await f.call('/api/interactive/sessions',own.metadata,own.token)).status,200);
});

test('withdrawn, technical-test and pre-listener-code sessions reserve no nickname',async t=>{
 const f=setup(t);
 const technical=f.listening('tech_name',A,{participant_id:'TEST-'+'C'.repeat(32),record_type:'technical_test',eligibility:{comfortable_english:false,headphones:false,previously_used_studio:false}});
 assert.equal((await f.call('/api/study/sessions',technical)).status,200);
 assert.equal((await f.check('tech_name',B)).available,true);
 assert.equal((await f.call('/api/study/sessions',f.listening('legacy_name',null))).status,200);
 assert.equal((await f.check('legacy_name',B)).available,true);
 const gone=f.listening('gone_name',A),token=newSessionToken();
 assert.equal((await f.call('/api/study/sessions',gone,token)).status,200);
 assert.equal((await f.call(`/api/study/sessions/${gone.participant_id}`,undefined,token,'DELETE')).status,200);
 assert.equal((await f.check('gone_name',B)).available,true);
});

test('the check validates its input, fails open offline, and every nickname field shows the red message',async t=>{
 const f=setup(t);
 assert.equal((await f.call('/api/nicknames/check',{nickname:'x',listener_id:A})).status,400);
 assert.equal((await f.call('/api/nicknames/check',{nickname:'valid_name',listener_id:'not-a-code'})).status,400);
 assert.equal(await nicknameAvailable('anna_07',A,async()=>{throw new Error('offline');}),true);
 assert.equal(await nicknameAvailable('anna_07',A,async()=>new Response(JSON.stringify({available:false}),{status:200})),false);
 for(const [page,element] of [['index.html','id="entry-error" role="alert"'],['listen.html','id="study-nickname-error" class="nickname-error" role="alert"'],['studio.html','id="nickname-error" class="nickname-error" role="alert"']])assert.ok(read(page).includes(element),page);
 for(const script of ['home.js','listen.js','app.js'])assert.match(read(script),/nicknameAvailable\(/,script);
 assert.match(read('style.css'),/\.nickname-error\{[^}]*color:#a42525/);
 // A check reads the database only, so the Space proxy saves no snapshot for it.
 assert.match(read('deployment/huggingface/web_host.py'),/path!='\/api\/nicknames\/check'/);
});

// The author asked for "Thursday afternoon" back in the default phrase (2026-09-14).
test('Test mode starts with the default phrase that says Thursday afternoon',()=>{
 const studio=read('studio.html');
 assert.ok(studio.includes('required>The meeting has been moved to Thursday afternoon. I will see you there.</textarea>'));
 assert.ok(!studio.includes('moved to Thursday. I will'));
});
