// Researcher export: one folder per listener, one per activity inside it, and one per session inside that, each with
// metadata.json and, for Test and Explore, the archived voice recordings.
//
//   node scripts/export-listeners.mjs --bucket <folder with snapshots/ and audio/> --out <new folder> [--include-technical]
//   node scripts/export-listeners.mjs --database <study.sqlite> [--audio <audio folder>] --out <new folder> [--include-technical]
//
// --bucket reads the newest verified snapshot, for example the echo/ folder of the downloaded Hugging Face research bucket.
// For a running local installation, export from a copy made with scripts/backup.mjs.
import {DatabaseSync} from 'node:sqlite';
import {createHash} from 'node:crypto';
import {copyFileSync,existsSync,mkdirSync,readdirSync,readFileSync,writeFileSync} from 'node:fs';
import {basename,dirname,join,resolve} from 'node:path';
import {pathToFileURL} from 'node:url';
import {parseArgs} from 'node:util';
import current from '../public/study/manifest.json' with {type:'json'};
import previous from '../public/study/manifest-v4.json' with {type:'json'};

export const EXPORT_VERSION='echo-listener-export-v2';
export const ACTIVITY_FOLDERS={line:'test-mode',explore:'explore-mode'};
const LISTENER=/^L-[A-F0-9]{32}$/,AUDIO_KEY=/^interactive\/X-[A-F0-9]{32}\/[0-9]+-[a-f0-9]{64}\.wav$/;
const manifests=new Map([current,previous].map(m=>[m.study_version,m]));
const sha=file=>createHash('sha256').update(readFileSync(file)).digest('hex');
const writeJson=(file,data)=>writeFileSync(file,JSON.stringify(data,null,2)+'\n',{mode:0o600});
// Session folder names sort by time and are valid on Windows, e.g. 2026-09-12T10-27-10Z.
const stamp=utc=>Number.isFinite(Date.parse(utc))?new Date(utc).toISOString().replace(/\.\d{3}Z$/,'Z').replaceAll(':','-'):'unknown-time';
const internalId=seed=>'I-'+createHash('sha256').update(seed).digest('hex').slice(0,32).toUpperCase();
export const normalNickname=value=>String(value??'').normalize('NFC').trim().toLowerCase();

export const LISTENER_ID_RULES={
 browser_code:'The random code the browser kept beside the nickname.',
 nickname_match:'No browser code; the nickname belongs to exactly one browser code, so the session joins that listener.',
 nickname:'No browser code; an internal ID derived from the nickname, which listeners are asked to keep throughout their participation.',
 session:'No browser code, and the nickname is blank or used by several listeners; an internal ID for this session alone.'
};

// Gives every exported session a listener ID (L-… from the browser, or an internal, repeatable I-…).
// A nickname counts as used by several listeners when it carries more than one browser code, or when more than one
// Listening session carries it under different or missing codes: each listener takes the Listening test once.
export function assignListeners(sessions){
 const byNickname=new Map(),code=s=>LISTENER.test(s.listener_id||'')?s.listener_id:null;
 for(const s of sessions){
  const nickname=normalNickname(s.nickname);if(!nickname)continue;
  const entry=byNickname.get(nickname)||{codes:new Set(),listening:new Set()};byNickname.set(nickname,entry);
  if(code(s))entry.codes.add(code(s));
  if(s.activity==='listening-test')entry.listening.add(code(s)||`session:${s.session_id}`);
 }
 return new Map(sessions.map(s=>{
  const nickname=normalNickname(s.nickname),entry=byNickname.get(nickname);
  if(code(s))return [s.session_id,{listener_id:code(s),source:'browser_code'}];
  if(!entry||entry.codes.size>1||entry.listening.size>1)return [s.session_id,{listener_id:internalId(`session:${s.session_id}`),source:'session'}];
  if(entry.codes.size===1)return [s.session_id,{listener_id:[...entry.codes][0],source:'nickname_match'}];
  return [s.session_id,{listener_id:internalId(`nickname:${nickname}`),source:'nickname'}];
 }));
}

// The newest snapshot the Hugging Face host wrote, checked against its manifest.
export function newestSnapshot(bucket){
 const folder=join(bucket,'snapshots'),markers=existsSync(folder)?readdirSync(folder).filter(f=>f.endsWith('.json')).sort():[];
 if(!markers.length)throw new Error(`No snapshot manifests in ${folder}.`);
 const marker=JSON.parse(readFileSync(join(folder,markers.at(-1)),'utf8')),database=join(folder,basename(String(marker.database)));
 if(!existsSync(database)||sha(database)!==marker.sha256)throw new Error(`The newest snapshot ${marker.database} is missing or does not match its checksum.`);
 return {database,audio:join(bucket,'audio'),snapshot:markers.at(-1)};
}

// Which clip or message was started first, and how often each was paused, finished, sought and replayed after finishing.
// Browsers also report a pause when a clip reaches its end.
export function listeningSummary(events){
 const items=new Map(),order=[];
 for(const e of events){
  let s=items.get(e.item_order);
  if(!s){s={item_order:e.item_order,item_id:e.item_id??null,plays:0,replays:0,finishes:0,pauses:0,seeks:0,first_play_utc:null,last_event_utc:null};items.set(e.item_order,s);}
  if(e.event==='play'){if(!s.plays)order.push(e.item_order);if(s.finishes)s.replays++;s.plays++;s.first_play_utc??=e.client_utc;}
  else if(e.event==='ended')s.finishes++;else if(e.event==='pause')s.pauses++;else if(e.event==='seeked')s.seeks++;
  s.last_event_utc=e.client_utc;
 }
 return {first_play_order:order,per_item:[...items.values()].sort((a,b)=>a.item_order-b.item_order)};
}

export function exportListeners({database,audio,out,includeTechnical=false,snapshot=null}){
 const target=resolve(out);
 if(existsSync(target)&&readdirSync(target).length)throw new Error(`${target} is not empty. Choose a new folder.`);
 mkdirSync(target,{recursive:true,mode:0o700});
 const db=new DatabaseSync(database,{readOnly:true}),listeners=new Map(),warnings=[],sessions={'listening-test':0,'test-mode':0,'explore-mode':0},sources={};let recordings=0;
 try{
  const hasTable=name=>Boolean(db.prepare("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?").get(name));
  const hasColumn=(table,name)=>db.prepare(`PRAGMA table_info(${table})`).all().some(c=>c.name===name);
  // Snapshots from before listener codes and playback events still export, with internal IDs and without events.
  const listenerColumn=table=>hasColumn(table,'listener_id')?'listener_id':'NULL AS listener_id';
  const events=hasTable('playback_events')?db.prepare('SELECT seq,event,item_order,item_id,position_s,duration_s,playback_rate,autoplay,client_utc,received_utc FROM playback_events WHERE session_kind=? AND session_id=? ORDER BY seq,client_utc'):null;
  const playback=(kind,id)=>events?events.all(kind,id).map(e=>({...e,autoplay:Boolean(e.autoplay)})):[];
  const human=includeTechnical?'':" AND record_type<>'technical_test'";
  const studyRows=db.prepare(`SELECT *,${listenerColumn('study_sessions')} FROM study_sessions WHERE withdrawn_utc IS NULL${human} ORDER BY received_utc`).all();
  const interactiveRows=db.prepare(`SELECT *,${listenerColumn('interactive_sessions')} FROM interactive_sessions WHERE withdrawn_utc IS NULL${human} ORDER BY received_utc`).all();
  for(const s of interactiveRows)if(!ACTIVITY_FOLDERS[s.mode])warnings.push(`${s.session_id}: unknown mode ${s.mode}, not exported`);
  const interactive=interactiveRows.filter(s=>ACTIVITY_FOLDERS[s.mode]);
  const ids=assignListeners([...studyRows.map(s=>({activity:'listening-test',session_id:s.participant_id,listener_id:s.listener_id,nickname:s.nickname})),
   ...interactive.map(s=>({activity:ACTIVITY_FOLDERS[s.mode],session_id:s.session_id,listener_id:s.listener_id,nickname:s.nickname}))]);
  const folderFor=(s,activity,id)=>{
   const {listener_id,source}=ids.get(id),inside=`${activity}/${stamp(s.received_utc)}_${id}`,folder=join(target,listener_id,...inside.split('/'));
   mkdirSync(folder,{recursive:true,mode:0o700});
   const entry=listeners.get(listener_id)||{nicknames:new Set(),sources:new Set(),sessions:[]};listeners.set(listener_id,entry);
   entry.nicknames.add(s.nickname);entry.sources.add(source);sources[source]=(sources[source]||0)+1;
   entry.sessions.push({activity,folder:inside,session_id:id,record_type:s.record_type,nickname:s.nickname,listener_id_source:source,first_saved_utc:s.received_utc});
   sessions[activity]++;return {folder,listener:{listener_id,listener_id_source:source,browser_listener_code:LISTENER.test(s.listener_id||'')?s.listener_id:null}};
  };

  for(const s of studyRows){
   const manifest=manifests.get(s.study_version),items=new Map((manifest?.items||[]).map(i=>[i.item_id,i])),log=playback('study',s.participant_id);
   const {folder,listener}=folderFor(s,'listening-test',s.participant_id);
   const clips=db.prepare('SELECT * FROM study_responses WHERE participant_id=? ORDER BY trial_order').all(s.participant_id).map(r=>({order:r.trial_order,item_id:r.item_id,text_id:items.get(r.item_id)?.text_id??null,audio:items.get(r.item_id)?.audio??null,audio_sha256:items.get(r.item_id)?.sha256??null,block_id:r.block_id,valence:r.valence,arousal:r.arousal,naturalness:r.naturalness,target_match:r.target_match,play_count:r.play_count,completed_audio:Boolean(r.completed_audio),elapsed_s:r.elapsed_s,rated_utc:r.created_utc,received_utc:r.received_utc}));
   writeJson(join(folder,'metadata.json'),{export_version:EXPORT_VERSION,activity:'listening-test',...listener,nickname:s.nickname,session_id:s.participant_id,record_type:s.record_type,study_version:s.study_version,collection_version:s.collection_version,rating_scale:s.rating_scale,group:s.group_number,seed:s.seed,
    eligibility:{comfortable_english:Boolean(s.comfortable_english),headphones:Boolean(s.headphones),previously_used_studio:Boolean(s.previously_used_studio)},consent_utc:s.consent_utc,first_saved_utc:s.received_utc,last_saved_utc:s.updated_utc,completed_utc:s.completed_utc,
    trials_per_session:manifest?.trials_per_session??null,clips,listening:listeningSummary(log),playback_events:log});
  }

  const archivedQuery=hasTable('interactive_audio')?db.prepare('SELECT * FROM interactive_audio WHERE session_id=?'):null;
  for(const s of interactive){
   const activity=ACTIVITY_FOLDERS[s.mode],{folder,listener}=folderFor(s,activity,s.session_id),log=playback('interactive',s.session_id);
   const ratings=new Map(db.prepare('SELECT turn_order,rating_json FROM interactive_ratings WHERE session_id=?').all(s.session_id).map(r=>[r.turn_order,JSON.parse(r.rating_json)]));
   const archived=new Map((archivedQuery?archivedQuery.all(s.session_id):[]).map(a=>[a.turn_order,a]));
   const messages=db.prepare('SELECT * FROM interactive_turns WHERE session_id=? ORDER BY turn_order').all(s.session_id).map(t=>{
    const turn=JSON.parse(t.turn_json),a=archived.get(t.turn_order);let audio_file=null,audio_problem=a?null:'not_archived';
    if(a){
     const source=AUDIO_KEY.test(a.object_key)?join(audio,...a.object_key.split('/')):null,name=`${String(t.turn_order).padStart(2,'0')}_${t.engine}_${t.emotion}.wav`;
     if(!source||!existsSync(source))audio_problem='missing';else if(sha(source)!==a.sha256)audio_problem='checksum_mismatch';else{copyFileSync(source,join(folder,name));audio_file=name;recordings++;}
     if(audio_problem)warnings.push(`${s.session_id} message ${t.turn_order}: recording ${audio_problem.replace('_',' ')}`);
    }
    return {order:t.turn_order,engine:t.engine,emotion:t.emotion,input_text:t.input_text,output_text:t.output_text,created_utc:t.created_utc,received_utc:t.received_utc,audio_file,audio_problem,audio_sha256:turn.audio_sha256??null,duration_s:turn.duration_s??null,
     generation_elapsed_s:turn.elapsed_s??null,controls:turn.controls??null,audio_metrics:turn.audio_metrics??null,generation_metadata:turn.generation_metadata??null,rating:ratings.get(t.turn_order)??null};
   });
   writeJson(join(folder,'metadata.json'),{export_version:EXPORT_VERSION,activity,...listener,nickname:s.nickname,session_id:s.session_id,record_type:s.record_type,mode:s.mode,engine:s.engine,version:s.version,
    consent_utc:s.consent_utc,first_saved_utc:s.received_utc,last_saved_utc:s.updated_utc,messages,listening:listeningSummary(log),playback_events:log});
  }

  for(const [listener_id,entry] of listeners)writeJson(join(target,listener_id,'listener.json'),{export_version:EXPORT_VERSION,listener_id,listener_id_sources:[...entry.sources].sort(),
   nicknames:[...entry.nicknames].filter(Boolean).sort(),sessions:entry.sessions.sort((a,b)=>String(a.first_saved_utc).localeCompare(String(b.first_saved_utc)))});
  const summary={export_version:EXPORT_VERSION,exported_utc:new Date().toISOString(),source:{database:basename(database),database_sha256:sha(database),snapshot},include_technical:includeTechnical,listeners:listeners.size,sessions,
   listener_id_sources:sources,listener_id_rules:LISTENER_ID_RULES,recordings_copied:recordings,warnings};
  writeJson(join(target,'export.json'),summary);
  return summary;
 }finally{db.close();}
}

if(process.argv[1]&&import.meta.url===pathToFileURL(resolve(process.argv[1])).href){
 const {values}=parseArgs({options:{bucket:{type:'string'},database:{type:'string'},audio:{type:'string'},out:{type:'string'},'include-technical':{type:'boolean',default:false}}});
 if(!values.out||!values.bucket===!values.database){console.error('Usage: node scripts/export-listeners.mjs (--bucket <folder> | --database <study.sqlite> [--audio <folder>]) --out <new folder> [--include-technical]');process.exit(1);}
 try{
  const input=values.bucket?newestSnapshot(resolve(values.bucket)):{database:resolve(values.database),audio:resolve(values.audio||join(dirname(resolve(values.database)),'audio')),snapshot:null};
  const summary=exportListeners({...input,out:values.out,includeTechnical:values['include-technical']});
  console.log(`Exported ${summary.listeners} listener folders: ${summary.sessions['listening-test']} listening, ${summary.sessions['test-mode']} test and ${summary.sessions['explore-mode']} explore sessions, ${summary.recordings_copied} recordings. Folder: ${resolve(values.out)}`);
  for(const warning of summary.warnings)console.warn('Warning: '+warning);
 }catch(error){console.error(error.message);process.exit(1);}
}
