import test from 'node:test';
import assert from 'node:assert/strict';
import {cpSync,mkdirSync,mkdtempSync,readFileSync,readdirSync,rmSync,writeFileSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {createHash} from 'node:crypto';
import {execFileSync} from 'node:child_process';
import worker,{COLLECTION_VERSION} from '../server/worker.js';
import {localDatabase} from '../server/local-db.js';
import {localAudio} from '../server/local-audio.js';
import {makeTrials,RATING_SCALE} from '../study-session.js';
import {StudySync,newSessionToken} from '../study-sync.js';
import {createInteractiveSession,InteractiveSync} from '../interactive-sync.js';
import {trackPlayback,trackTranscript} from '../playback-log.js';
import {listenerId,LISTENER_PATTERN} from '../listener.js';
import {audioResult,hashAudio} from '../audio-utils.js';
import {controlsFor} from '../voice-controls.js';
import {exportListeners,assignListeners,readCoverageLinks,LISTENING_CSV_FIELDS,APPLICATION_CSV_FIELDS} from '../scripts/export-listeners.mjs';
import manifest from '../public/study/manifest.json' with {type:'json'};

const origin='https://echo.example';
function site(t){
 const dir=mkdtempSync(join(tmpdir(),'echo-listener-'));const DB=localDatabase(join(dir,'study.sqlite')),AUDIO=localAudio(join(dir,'audio'));
 t.after(()=>{DB.close();rmSync(dir,{recursive:true,force:true});});
 const env={DB,AUDIO,RESEARCHER_AUTHORIZED:false};
 const fetcher=(path,options={})=>worker.fetch(new Request(origin+path,{...options,headers:{Origin:origin,...options.headers}}),env,{});
 const count=table=>DB.sqlite.prepare(`SELECT COUNT(*) AS n FROM ${table}`).get().n;
 return {dir,DB,fetcher,count};
}
const event=(item_order,type,overrides={})=>({event_id:crypto.randomUUID(),event:type,item_order,item_id:null,position_s:0,duration_s:2,playback_rate:1,autoplay:false,client_utc:new Date().toISOString(),...overrides});
function listeningSession(listener){
 return {nickname:'playback_listener',rating_scale:RATING_SCALE,participant_id:'TEST-'+crypto.randomUUID().replaceAll('-','').toUpperCase(),study_version:manifest.study_version,collection_version:COLLECTION_VERSION,record_type:'technical_test',group:2,seed:77,
  eligibility:{comfortable_english:true,headphones:true,previously_used_studio:false},consent:true,consent_utc:new Date().toISOString(),rows:[],listener_id:listener,remote:{token:newSessionToken(),consent_utc:new Date().toISOString(),saved_count:0}};
}
const rated=(trials,index)=>({order:index+1,item_id:trials[index].item_id,block_id:trials[index].block_id,valence:.1,arousal:-.2,naturalness:3,target_match:4,play_count:1,completed_audio:true,elapsed_s:5,created_utc:new Date().toISOString()});
async function voice(){
 const samples=Float32Array.from({length:24000},(_,n)=>.1*Math.sin(n*2*Math.PI*150/24000)),result=audioResult(samples,24000,1),sha=await hashAudio(result.buffer);
 return {buffer:result.buffer,sha,turn:{order:1,engine:'kokoro',emotion:'happy',input_text:'Hello there.',output_text:'Hello! What a lovely day.',controls:controlsFor({engine:'kokoro',emotion:'happy'}),audio_metrics:{},audio_sha256:sha,duration_s:1,elapsed_s:2,created_utc:new Date().toISOString()}};
}
const readCsv=file=>{const [header,...rows]=readFileSync(file,'utf8').trim().split('\r\n').map(line=>line.split(','));return {header,rows:rows.map(r=>Object.fromEntries(header.map((h,i)=>[h,r[i]])))};};

test('a listener code is random, well formed and stable within one page',()=>{
 const id=listenerId();assert.match(id,LISTENER_PATTERN);assert.equal(listenerId(),id);
});

test('the playback tracker records play, pause, finish and seek with position, speed and autoplay',()=>{
 const audio=Object.assign(new EventTarget(),{currentTime:0,duration:2.5,playbackRate:1,dataset:{autoplay:'1'}}),events=[];
 trackPlayback(audio,()=>({item_order:3,item_id:'clip'}),e=>events.push(e));
 audio.dispatchEvent(new Event('play'));audio.currentTime=1.23456;audio.dispatchEvent(new Event('pause'));audio.currentTime=2.5;audio.dispatchEvent(new Event('ended'));
 audio.currentTime=.5;audio.dispatchEvent(new Event('seeked'));audio.dispatchEvent(new Event('play'));
 assert.deepEqual(events.map(e=>[e.event,e.position_s,e.autoplay]),[['play',0,true],['pause',1.235,false],['ended',2.5,false],['seeked',.5,false],['play',.5,false]]);
 assert.ok(events.every(e=>e.item_order===3&&e.item_id==='clip'&&e.duration_s===2.5&&e.playback_rate===1&&/^[0-9a-f-]{36}$/.test(e.event_id)&&Number.isFinite(Date.parse(e.client_utc))));
 let heard=0;const idle=Object.assign(new EventTarget(),{currentTime:0,duration:NaN,playbackRate:1,dataset:{}});trackPlayback(idle,()=>null,()=>heard++);idle.dispatchEvent(new Event('play'));assert.equal(heard,0);
});

test('the transcript tracker records opening and closing with the voice position',()=>{
 const button=new EventTarget(),transcript={hidden:true},audio={currentTime:.8,duration:2,playbackRate:1,dataset:{}},events=[];
 button.addEventListener('click',()=>{transcript.hidden=!transcript.hidden;});
 trackTranscript(button,transcript,audio,()=>({item_order:2}),e=>events.push(e));
 button.dispatchEvent(new Event('click'));audio.currentTime=2;button.dispatchEvent(new Event('click'));
 assert.deepEqual(events.map(e=>[e.event,e.item_order,e.position_s,e.duration_s]),[['transcript_open',2,.8,2],['transcript_close',2,2,2]]);
});

test('Listening playback travels with saves, must name the assigned clip, is idempotent and is deleted on withdrawal',async t=>{
 const f=site(t),listener='L-'+'A'.repeat(32),s=listeningSession(listener),trials=makeTrials(manifest,s.group,s.seed);
 const auth={Authorization:`Bearer ${s.remote.token}`,'Content-Type':'application/json'},post=(path,data,headers=auth)=>f.fetcher(path,{method:'POST',headers,body:JSON.stringify(data)});
 assert.equal((await post('/api/study/sessions',{...s,listener_id:'L-not-a-code'})).status,400);
 const sync=new StudySync({session:s,trials,fetcher:f.fetcher});
 sync.playback(event(1,'play',{item_id:trials[0].item_id}));sync.playback(event(1,'ended',{item_id:trials[0].item_id,position_s:2}));
 s.rows.push(rated(trials,0));await sync.sync();
 assert.deepEqual(s.playback,[]);
 assert.deepEqual(f.DB.sqlite.prepare("SELECT seq,event,item_order,item_id FROM playback_events WHERE session_kind='study' ORDER BY seq").all().map(e=>[e.seq,e.event,e.item_order,e.item_id]),[[1,'play',1,trials[0].item_id],[2,'ended',1,trials[0].item_id]]);
 assert.equal(f.DB.sqlite.prepare('SELECT listener_id FROM study_sessions').get().listener_id,listener);
 const path=`/api/study/sessions/${s.participant_id}/playback`,again={events:[{...event(1,'play',{item_id:trials[0].item_id}),seq:3}]};
 for(let n=0;n<2;n++)assert.equal((await post(path,again)).status,200);
 assert.equal(f.count('playback_events'),3);
 assert.equal((await post(path,{events:[{...event(1,'play',{item_id:trials[1].item_id}),seq:4}]})).status,400);
 assert.equal((await post(path,{events:[{...event(1,'scrub',{item_id:trials[0].item_id}),seq:4}]})).status,400);
 assert.equal((await post(path,{events:[{...event(1,'transcript_open',{item_id:trials[0].item_id}),seq:4}]})).status,400);
 assert.equal((await post(path,again,{...auth,Authorization:`Bearer ${newSessionToken()}`})).status,403);
 assert.equal((await f.fetcher(`/api/study/sessions/${s.participant_id}`,{method:'DELETE',headers:auth})).status,200);
 assert.equal(f.count('playback_events'),0);
});

test('a playback event the server rejects is dropped without blocking the saved responses',async t=>{
 const f=site(t),s=listeningSession(listenerId()),trials=makeTrials(manifest,s.group,s.seed),states=[];
 const sync=new StudySync({session:s,trials,fetcher:f.fetcher,onStatus:x=>states.push(x.state)});
 sync.playback(event(1,'play',{item_id:'not-the-assigned-clip'}));s.rows.push(rated(trials,0));await sync.sync();
 assert.equal(states.at(-1),'saved');assert.deepEqual(s.playback,[]);assert.equal(s.playback_rejected,1);assert.equal(f.count('study_responses'),1);assert.equal(f.count('playback_events'),0);
});

test('sessions saved before listener codes are linked once, and a code is never replaced',async t=>{
 const f=site(t),session=createInteractiveSession('explore','legacy_listener','chatterbox','female');delete session.listener_id;
 const post=data=>f.fetcher('/api/interactive/sessions',{method:'POST',headers:{Authorization:`Bearer ${session.token}`,'Content-Type':'application/json'},body:JSON.stringify(data)});
 assert.equal((await post(session)).status,200);assert.equal(f.DB.sqlite.prepare('SELECT listener_id FROM interactive_sessions').get().listener_id,null);
 const first='L-'+'B'.repeat(32);assert.equal((await post({...session,listener_id:first})).status,200);assert.equal((await post({...session,listener_id:'L-'+'C'.repeat(32)})).status,200);
 assert.equal(f.DB.sqlite.prepare('SELECT listener_id FROM interactive_sessions').get().listener_id,first);
 assert.equal((await post({...session,listener_id:'nickname'})).status,400);
});

test('Test and Explore playback waits for its message, travels with saves and is deleted on withdrawal',async t=>{
 const f=site(t),session=createInteractiveSession('explore','playback_explorer','kokoro','male'),{buffer,turn}=await voice(),sync=new InteractiveSync(session,{fetcher:f.fetcher});
 sync.playback(event(1,'play',{autoplay:true}));await sync.add(turn,buffer);
 assert.deepEqual(session.playback,[]);
 sync.playback(event(1,'pause',{position_s:.4}));sync.playback(event(2,'play'));await sync.sync();
 assert.deepEqual(session.playback.map(e=>e.item_order),[2]);
 assert.deepEqual(f.DB.sqlite.prepare("SELECT seq,event,item_order,autoplay FROM playback_events WHERE session_kind='interactive' ORDER BY seq").all().map(e=>[e.seq,e.event,e.item_order,e.autoplay]),[[1,'play',1,1],[2,'pause',1,0]]);
 const base=`/api/interactive/sessions/${session.session_id}`,headers={Authorization:`Bearer ${session.token}`,'Content-Type':'application/json'},post=data=>f.fetcher(base+'/playback',{method:'POST',headers,body:JSON.stringify(data)});
 assert.equal((await post({events:[{...event(5,'play'),seq:9}]})).status,400);
 assert.equal((await post({events:[{...event(1,'play',{item_id:'clip'}),seq:9}]})).status,400);
 assert.equal((await post({events:[{...event(1,'transcript_open',{position_s:.3}),seq:10}]})).status,200);
 assert.equal((await f.fetcher(base,{method:'DELETE',headers})).status,200);
 assert.equal(f.count('playback_events'),0);
});

test('listeners are grouped by coverage sheet, browser code and nickname, and named by their Listening participant code',()=>{
 const A='L-'+'A'.repeat(32),B='L-'+'B'.repeat(32),C='L-'+'C'.repeat(32);
 const S=(activity,session_id,listener_id,nickname)=>({activity,session_id,listener_id,nickname,first_saved_utc:'2026-09-12T10:00:00Z'});
 const sessions=[
  S('listening-test','P-1',A,'mira'),S('explore-mode','X-1',null,' Mira '),
  S('listening-test','P-2',null,'oleh'),S('test-mode','X-2',null,'OLEH'),
  S('listening-test','P-3',null,'listener_07'),S('listening-test','P-4',B,'listener_07'),S('explore-mode','X-3',null,'listener_07'),
  S('explore-mode','X-4',null,''),
  S('listening-test','P-5',C,'ana'),S('explore-mode','X-5',C,'bo'),
  S('explore-mode','X-6',null,'someone_else')
 ];
 const links=new Map([['X-6','P-3']]),ids=assignListeners(sessions,{links}),pick=id=>[ids.get(id).listener_id,ids.get(id).source];
 assert.deepEqual(pick('P-1'),['P-1','browser_code']);assert.deepEqual(pick('X-1'),['P-1','nickname_match']);
 assert.deepEqual(pick('P-2'),['P-2','nickname']);assert.deepEqual(pick('X-2'),['P-2','nickname']);
 assert.deepEqual(pick('P-3'),['P-3','session']);assert.deepEqual(pick('P-4'),['P-4','browser_code']);
 assert.equal(ids.get('X-3').source,'session');assert.match(ids.get('X-3').listener_id,/^I-[A-F0-9]{32}$/);
 assert.equal(ids.get('X-4').source,'session');assert.notEqual(ids.get('X-4').listener_id,ids.get('X-3').listener_id);
 assert.deepEqual(pick('P-5'),['P-5','browser_code']);assert.deepEqual(pick('X-5'),[C,'browser_code']);
 assert.deepEqual(pick('X-6'),['P-3','coverage_sheet']);
 assert.deepEqual(assignListeners(sessions,{links}).get('X-3'),ids.get('X-3'));
});

test('coverage sheets link sessions to Listening participants; conflicting and unreadable links are left out',t=>{
 const dir=mkdtempSync(join(tmpdir(),'echo-coverage-'));t.after(()=>rmSync(dir,{recursive:true,force:true}));
 const X1='X-'+'1'.repeat(32),X2='X-'+'2'.repeat(32),X3='X-'+'3'.repeat(32),P='P-'+'A'.repeat(32),Q='P-'+'B'.repeat(32);
 writeFileSync(join(dir,'one.csv'),`﻿task_id,nickname,listening_participant_id,mode,session_id,turn_order,incident_or_comment\r\nT01,mira,${P},Test,${X1},1,"slow, but ""fine"""\r\nE01,mira,${P.toLowerCase()},Explore,${X2.toLowerCase()},1,\r\nE02,mira,${P},Explore,${X3},1,\r\nT02,mira,,Test,,,\r\nT03,mira,P-XYZ,Test,${X1},2,\r\n`);
 writeFileSync(join(dir,'two.csv'),`task_id,listening_participant_id,session_id\r\nE01,${Q},${X3}\r\n`);
 const sheets=readCoverageLinks([dir]);
 assert.equal(sheets.files,2);assert.deepEqual([...sheets.links.entries()].sort(),[[X1,P],[X2,P]]);assert.deepEqual(sheets.conflicts,[X3]);assert.equal(sheets.invalid.length,1);
 writeFileSync(join(dir,'bad.csv'),'task_id,session_id\r\n');assert.throws(()=>readCoverageLinks([join(dir,'bad.csv')]),/not a coverage sheet/);
});

test('the researcher export builds listener, activity and timestamped session folders, metadata, recordings and playback CSVs',async t=>{
 const f=site(t),listener=listenerId();
 const s=listeningSession(listener),trials=makeTrials(manifest,s.group,s.seed),study=new StudySync({session:s,trials,fetcher:f.fetcher});
 study.playback(event(1,'play',{item_id:trials[0].item_id}));study.playback(event(1,'ended',{item_id:trials[0].item_id,position_s:2}));study.playback(event(2,'play',{item_id:trials[1].item_id}));
 s.rows.push(rated(trials,0),rated(trials,1));await study.sync();
 const chat=createInteractiveSession('explore','playback_listener','kokoro','na'),{buffer,sha,turn}=await voice(),explore=new InteractiveSync(chat,{fetcher:f.fetcher});
 await explore.add(turn,buffer);await explore.rate(1,{valence:.2,arousal:.3,naturalness:4,target_match:4,rating_scale:RATING_SCALE,version:'echo-message-rating-v1',completed_audio:true,play_count:2,elapsed_s:8,created_utc:new Date().toISOString()});
 explore.playback(event(1,'play',{autoplay:true}));explore.playback(event(1,'transcript_open',{position_s:.5}));explore.playback(event(1,'ended',{position_s:1}));explore.playback(event(1,'play'));await explore.sync();
 const legacy=createInteractiveSession('line','earlier_visitor',null,'female');delete legacy.listener_id;
 await new InteractiveSync(legacy,{fetcher:f.fetcher}).add({...turn,input_text:'An earlier test.',output_text:'An earlier test.'});
 const database=join(f.dir,'study.sqlite'),audio=join(f.dir,'audio'),out=join(f.dir,'export'),P=s.participant_id;

 const human=exportListeners({database,audio,out:join(f.dir,'export-human')});
 assert.deepEqual(human.sessions,{'listening-test':0,'test-mode':1,'explore-mode':1});
 assert.ok(readdirSync(join(f.dir,'export-human')).includes(listener));

 const all=exportListeners({database,audio,out,includeTechnical:true});
 assert.deepEqual(all.sessions,{'listening-test':1,'test-mode':1,'explore-mode':1});assert.equal(all.recordings_copied,1);assert.deepEqual(all.warnings,[]);
 assert.deepEqual(all.listener_id_sources,{browser_code:2,nickname:1});
 const earlierId=assignListeners([{activity:'test-mode',session_id:legacy.session_id,listener_id:null,nickname:'earlier_visitor'}]).get(legacy.session_id).listener_id;
 assert.match(earlierId,/^I-[A-F0-9]{32}$/);
 assert.deepEqual(readdirSync(out).sort(),[P,earlierId,'application-playback.csv','export.json','listening-playback.csv'].sort());
 assert.deepEqual(readdirSync(join(out,P)).sort(),['explore-mode','listener.json','listening-test']);

 const [chatFolder]=readdirSync(join(out,P,'explore-mode'));assert.match(chatFolder,new RegExp(`^\\d{4}-\\d{2}-\\d{2}T\\d{2}-\\d{2}-\\d{2}Z_${chat.session_id}$`));
 const conversation=JSON.parse(readFileSync(join(out,P,'explore-mode',chatFolder,'metadata.json'),'utf8'));
 assert.equal(conversation.listener_id,P);assert.equal(conversation.listener_id_source,'browser_code');assert.equal(conversation.browser_listener_code,listener);assert.deepEqual(conversation.listening_participant_codes,[P]);
 assert.equal(conversation.activity,'explore-mode');assert.equal(conversation.messages[0].audio_file,'01_kokoro_happy.wav');assert.equal(conversation.messages[0].rating.target_match,4);
 assert.deepEqual(conversation.playback_events.map(e=>[e.seq,e.event,e.autoplay]),[[1,'play',true],[2,'transcript_open',false],[3,'ended',false],[4,'play',false]]);
 const message=conversation.listening.per_item[0];assert.deepEqual([message.plays,message.replays,message.finishes,message.transcript_opens,message.transcript_opened_before_finish],[2,1,1,1,true]);
 assert.equal(await hashAudio(readFileSync(join(out,P,'explore-mode',chatFolder,'01_kokoro_happy.wav'))),sha);

 const [studyFolder]=readdirSync(join(out,P,'listening-test'));const listening=JSON.parse(readFileSync(join(out,P,'listening-test',studyFolder,'metadata.json'),'utf8'));
 assert.equal(listening.session_id,P);assert.equal(listening.clips.length,2);assert.equal(listening.clips[0].audio,manifest.items.find(i=>i.item_id===trials[0].item_id).audio);
 assert.deepEqual(listening.listening.first_play_order,[1,2]);assert.equal(listening.playback_events.length,3);

 const trialsCsv=readCsv(join(out,'listening-playback.csv'));assert.deepEqual(trialsCsv.header,LISTENING_CSV_FIELDS);assert.equal(trialsCsv.rows.length,2);
 assert.deepEqual(['participant_id','order','audio_sha256','plays','finishes'].map(k=>trialsCsv.rows[0][k]),[P,'1',manifest.items.find(i=>i.item_id===trials[0].item_id).sha256,'1','1']);
 assert.deepEqual([trialsCsv.rows[1].plays,trialsCsv.rows[1].finishes],['1','0']);
 const messagesCsv=readCsv(join(out,'application-playback.csv'));assert.deepEqual(messagesCsv.header,APPLICATION_CSV_FIELDS);
 const chatRow=messagesCsv.rows.find(r=>r.session_id===chat.session_id),earlierRow=messagesCsv.rows.find(r=>r.session_id===legacy.session_id);
 assert.deepEqual(['listener_id','turn_order','rated','transcript_opens','transcript_opened_before_finish'].map(k=>chatRow[k]),[P,'1','true','1','true']);
 assert.deepEqual(['listener_id','plays','rated','transcript_opened_before_finish'].map(k=>earlierRow[k]),[earlierId,'0','false','']);

 const listenerFile=JSON.parse(readFileSync(join(out,P,'listener.json'),'utf8'));
 assert.deepEqual(listenerFile.listening_participant_codes,[P]);assert.deepEqual(listenerFile.browser_codes,[listener]);assert.deepEqual(listenerFile.sessions.map(x=>x.activity).sort(),['explore-mode','listening-test']);
 const earlier=JSON.parse(readFileSync(join(out,earlierId,'test-mode',readdirSync(join(out,earlierId,'test-mode'))[0],'metadata.json'),'utf8'));
 assert.equal(earlier.messages[0].audio_problem,'not_archived');assert.equal(earlier.listener_id_source,'nickname');assert.equal(earlier.browser_listener_code,null);
 assert.throws(()=>exportListeners({database,audio,out}),/not empty/);

 // The coverage sheet places the earlier Test session with the Listening participant.
 const sheet=join(f.dir,'coverage.csv');writeFileSync(sheet,`task_id,listening_participant_id,session_id,turn_order\r\nT01,${P},${legacy.session_id},1\r\n`);
 const linked=exportListeners({database,audio,out:join(f.dir,'export-linked'),includeTechnical:true,coverage:[sheet]});
 assert.equal(linked.listeners,1);assert.deepEqual(linked.listener_id_sources,{browser_code:2,coverage_sheet:1});assert.deepEqual(linked.warnings,[]);
 assert.deepEqual(readdirSync(join(f.dir,'export-linked',P)).sort(),['explore-mode','listener.json','listening-test','test-mode']);

 // The Hugging Face bucket layout: the newest verified snapshot and the audio folder beside it.
 const bucket=join(f.dir,'bucket'),snapshot=join(bucket,'snapshots','01000000000000000002-test.sqlite');mkdirSync(join(bucket,'snapshots'),{recursive:true});
 f.DB.sqlite.exec(`VACUUM INTO '${snapshot.replaceAll("'","''")}'`);cpSync(audio,join(bucket,'audio'),{recursive:true});
 writeFileSync(join(bucket,'snapshots','01000000000000000002-test.json'),JSON.stringify({version:1,database:'01000000000000000002-test.sqlite',sha256:createHash('sha256').update(readFileSync(snapshot)).digest('hex'),audio:[]}));
 const printed=execFileSync(process.execPath,['scripts/export-listeners.mjs','--bucket',bucket,'--out',join(f.dir,'from-bucket'),'--include-technical','--coverage',sheet],{encoding:'utf8'});
 assert.match(printed,/Exported 1 listener folders: 1 listening, 1 test and 1 explore sessions, 1 recordings/);
 writeFileSync(join(bucket,'snapshots','01000000000000000003-bad.json'),JSON.stringify({version:1,database:'01000000000000000002-test.sqlite',sha256:'0'.repeat(64),audio:[]}));
 assert.throws(()=>execFileSync(process.execPath,['scripts/export-listeners.mjs','--bucket',bucket,'--out',join(f.dir,'refused')],{stdio:'pipe'}),/does not match its checksum/);
});

test('an export of a snapshot from before listener codes still works and assigns internal IDs',t=>{
 const dir=mkdtempSync(join(tmpdir(),'echo-old-export-'));t.after(()=>rmSync(dir,{recursive:true,force:true}));
 const database=join(dir,'old.sqlite'),DB=localDatabase(database);
 DB.sqlite.exec("INSERT INTO interactive_sessions (session_id,token_hash,nickname,mode,engine,record_type,version,consent_utc,received_utc,updated_utc) VALUES ('X-'||hex(randomblob(16)),'hash','old_visitor','explore','chatterbox','interactive_exploration','v','2026-09-10T10:00:00Z','2026-09-10T10:00:00Z','2026-09-10T10:00:00Z')");
 DB.sqlite.exec('DROP TABLE playback_events; DROP INDEX idx_interactive_sessions_listener; DROP INDEX idx_study_sessions_listener; ALTER TABLE interactive_sessions DROP COLUMN listener_id; ALTER TABLE study_sessions DROP COLUMN listener_id;');DB.close();
 const summary=exportListeners({database,audio:join(dir,'audio'),out:join(dir,'out')});
 assert.deepEqual(summary.sessions,{'listening-test':0,'test-mode':0,'explore-mode':1});
 const [id]=readdirSync(join(dir,'out')).filter(name=>!name.includes('.'));assert.match(id,/^I-[A-F0-9]{32}$/);
 const [folder]=readdirSync(join(dir,'out',id,'explore-mode'));assert.match(folder,/^2026-09-10T10-00-00Z_X-/);
 const metadata=JSON.parse(readFileSync(join(dir,'out',id,'explore-mode',folder,'metadata.json'),'utf8'));assert.deepEqual(metadata.playback_events,[]);assert.equal(metadata.listener_id_source,'nickname');
});
