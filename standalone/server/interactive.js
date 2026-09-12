import {audioUpload,deleteSessionAudio} from './audio.js';
import {validatePlayback,savePlayback,deletePlayback} from './playback.js';
import {LISTENER_PATTERN} from '../listener.js';
import {validateNickname,validateConversationTurn} from '../participant.js';
import {INTERACTIVE_VERSION} from '../interactive-sync.js';
import {controlsFor} from '../voice-controls.js';
import {TEST_ENGINES,EXPLORE_ENGINES} from '../engine-catalog.js';
import {validateMessageRating} from '../message-rating.js';
const ID=/^X-[A-F0-9]{32}$/;
const safeCell=value=>{const s=String(value??'');return '"'+(/^[\s]*[=+\-@]/.test(s)?"'"+s:s).replaceAll('"','""')+'"';};
export function explorationCSV(rows){const fields=['session_id','nickname','record_type','mode','turn_order','engine','emotion','input_text','output_text','created_utc','controls_json','audio_metrics_json','audio_sha256','duration_s','elapsed_s','end_to_end_tts_rtf','generation_metadata_json','audio_archive_status','audio_download_path','audio_stored_utc','rating_status','valence','arousal','naturalness','target_match','rating_scale','rating_version','rating_created_utc','completed_audio','play_count'];return [fields.join(','),...rows.map(r=>{const t=JSON.parse(r.turn_json||'{}'),rating=r.rating_json?JSON.parse(r.rating_json):{},record={...r,...rating,created_utc:r.created_utc,rating_status:r.rating_json?'rated':'not_rated',rating_version:rating.version,rating_created_utc:rating.created_utc,controls_json:JSON.stringify(t.controls||{}),audio_metrics_json:JSON.stringify(t.audio_metrics||{}),audio_sha256:t.audio_sha256,duration_s:t.duration_s,elapsed_s:t.elapsed_s,end_to_end_tts_rtf:t.duration_s>0?t.elapsed_s/t.duration_s:null,generation_metadata_json:JSON.stringify(t.generation_metadata||{}),audio_archive_status:r.audio_stored_utc?'archived':'not_archived',audio_download_path:r.audio_stored_utc?`/api/research/interactive/audio/${r.session_id}/${r.turn_order}`:''};return fields.map(k=>safeCell(record[k])).join(',');})].join('\r\n')+'\r\n';}
export async function interactiveApi(request,url,h){
 const {db,body,tokenHash,fail,json,now}=h,path=url.pathname;
 async function owned(id){if(!ID.test(id))fail(400,'Invalid conversation code.');const hash=await tokenHash(request),s=await db.prepare('SELECT * FROM interactive_sessions WHERE session_id=?').bind(id).first();if(!s||s.token_hash!==hash)fail(403,'This conversation needs its original browser credentials.');return s;}
 if(path==='/api/interactive/sessions'&&request.method==='POST'){
  const input=await body(request);if(!ID.test(input.session_id||''))fail(400,'Invalid conversation code.');
  let nickname;try{nickname=validateNickname(input.nickname);}catch(e){fail(400,e.message);}
  if(input.version!==INTERACTIVE_VERSION)fail(409,'Reload the prototype before starting this session.');
  if(!['line','explore'].includes(input.mode)||!['interactive_exploration','technical_test'].includes(input.record_type))fail(400,'Invalid session mode.');
  if(input.mode==='explore'?!EXPLORE_ENGINES.includes(input.engine):input.engine!==null)fail(400,'Choose one engine for an Explore conversation.');
  if(input.consent!==true||typeof input.consent_utc!=='string'||!Number.isFinite(Date.parse(input.consent_utc)))fail(400,'Agree to storage before continuing.');
  if(input.listener_id!=null&&!LISTENER_PATTERN.test(input.listener_id))fail(400,'Invalid listener code.');
  const timestamp=now(),hash=await tokenHash(request);
  if(!await db.prepare('SELECT 1 AS n FROM interactive_sessions WHERE session_id=?').bind(input.session_id).first()&&h.allowNewSession?.()===false)fail(429,'Too many new conversations from this network. Wait an hour and try again.');
  await db.prepare('INSERT INTO interactive_sessions (session_id,token_hash,nickname,mode,engine,record_type,version,consent_utc,received_utc,updated_utc,listener_id) VALUES (?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(session_id) DO NOTHING').bind(input.session_id,hash,nickname,input.mode,input.engine,input.record_type,input.version,input.consent_utc,timestamp,timestamp,input.listener_id??null).run();
  const s=await owned(input.session_id);if(s.withdrawn_utc)fail(410,'This conversation was deleted.');
  if(s.nickname!==nickname||s.mode!==input.mode||s.engine!==input.engine||s.version!==input.version||s.record_type!==input.record_type)fail(409,'Nickname and TTS engine are fixed for this conversation. Start a new one to change them.');
  // A conversation saved before listener codes existed is linked the first time its browser sends one; a code is never replaced.
  if(input.listener_id&&!s.listener_id)await db.prepare('UPDATE interactive_sessions SET listener_id=? WHERE session_id=? AND listener_id IS NULL').bind(input.listener_id,s.session_id).run();
  return json({session_id:s.session_id});
 }
 const audioRoute=path.match(/^\/api\/interactive\/sessions\/([^/]+)\/audio\/([1-9][0-9]?)$/);
 if(audioRoute){const session=await owned(audioRoute[1]);if(session.withdrawn_utc)fail(410,'This conversation was deleted.');if(request.method!=='PUT')fail(405,'Method not allowed.');return audioUpload(request,h,session,Number(audioRoute[2]));}
 const match=path.match(/^\/api\/interactive\/sessions\/([^/]+)(\/turns|\/ratings|\/attempts|\/playback)?$/);
 if(!match)fail(404,'Endpoint not found.');const s=await owned(match[1]);
 if(request.method==='DELETE'&&!match[2]){await db.prepare('UPDATE interactive_sessions SET withdrawn_utc=COALESCE(withdrawn_utc,?),nickname=\'\' WHERE session_id=?').bind(now(),s.session_id).run();await deleteSessionAudio(db,h.audioBucket,s.session_id);await db.prepare('DELETE FROM generation_attempts WHERE session_id=?').bind(s.session_id).run();await deletePlayback(db,'interactive',s.session_id).run();await db.prepare('DELETE FROM interactive_turns WHERE session_id=?').bind(s.session_id).run();return json({withdrawn:true});}
 if(s.withdrawn_utc)fail(410,'This conversation was deleted.');
 const read=async()=> (await db.prepare('SELECT * FROM interactive_turns WHERE session_id=? ORDER BY turn_order').bind(s.session_id).all()).results;
 if(request.method==='GET'&&!match[2]){const turns=await read(),ratings=(await db.prepare('SELECT turn_order,rating_json FROM interactive_ratings WHERE session_id=? ORDER BY turn_order').bind(s.session_id).all()).results;return json({session_id:s.session_id,nickname:s.nickname,mode:s.mode,engine:s.engine,saved_count:turns.length,turns:turns.map(t=>JSON.parse(t.turn_json)),ratings:ratings.map(r=>({order:r.turn_order,rating:JSON.parse(r.rating_json)}))});}
 if(request.method==='POST'&&match[2]==='/playback'){
  const events=validatePlayback(await body(request),{fail,maxOrder:s.mode==='explore'?10:12}),known=new Set((await read()).map(t=>t.turn_order));
  if(events.some(e=>!known.has(e.item_order)))fail(400,'Save the message before its playback events.');
  return json(await savePlayback(db,'interactive',s.session_id,events,now()));
 }
 if(request.method==='POST'&&match[2]==='/attempts'){
  const input=await body(request);if(!Array.isArray(input.attempts)||input.attempts.length>100)fail(400,'Too many generation attempts.');
  const existing=await db.prepare('SELECT COUNT(*) AS n FROM generation_attempts WHERE session_id=?').bind(s.session_id).first();
  if(existing.n>100)fail(400,'Start a new session for more attempts.');
  for(const raw of input.attempts){const e=Object.fromEntries(['attempt_id','engine','emotion','status','stage','elapsed_s','created_utc','turn_order'].map(k=>[k,raw[k]]));
   if(!/^[a-f0-9-]{36}$/.test(e.attempt_id||'')||!TEST_ENGINES.includes(e.engine)||!['happy','upset','sad','calm'].includes(e.emotion)||!['success','error','cancelled'].includes(e.status)||!['tts','dialogue','conversation'].includes(e.stage)||!Number.isFinite(e.elapsed_s)||e.elapsed_s<0||e.elapsed_s>86400||!Number.isFinite(Date.parse(e.created_utc))||!(e.turn_order===null||Number.isInteger(e.turn_order)&&e.turn_order>=1&&e.turn_order<=12))fail(400,'Invalid diagnostic record.');
   if(s.mode==='explore'&&e.engine!==s.engine)fail(400,'Wrong conversation engine.');
   await db.prepare('INSERT INTO generation_attempts (session_id,attempt_id,event_json,received_utc) SELECT ?,?,?,? WHERE EXISTS (SELECT 1 FROM interactive_sessions WHERE session_id=? AND withdrawn_utc IS NULL) AND (SELECT COUNT(*) FROM generation_attempts WHERE session_id=?)<100 ON CONFLICT(session_id,attempt_id) DO NOTHING').bind(s.session_id,e.attempt_id,JSON.stringify(e),now(),s.session_id,s.session_id).run();
  }
  const rows=(await db.prepare('SELECT attempt_id FROM generation_attempts WHERE session_id=?').bind(s.session_id).all()).results;return json({orders:rows.map(r=>r.attempt_id)});
 }
 if(request.method==='POST'&&match[2]==='/ratings'){
  const input=await body(request);if(!Array.isArray(input.ratings)||!input.ratings.length||input.ratings.length>12)fail(400,'Send 1–12 message ratings.');
  const known=new Set((await read()).map(t=>t.turn_order)),seen=new Set();
  const rows=input.ratings.map(raw=>{if(!Number.isInteger(raw.order)||!known.has(raw.order)||seen.has(raw.order))fail(400,'Each rating must identify one saved message.');seen.add(raw.order);
   const r=raw.rating||{},rating=Object.fromEntries(['valence','arousal','naturalness','target_match','rating_scale','version','completed_audio','play_count','elapsed_s','created_utc'].map(k=>[k,r[k]]));try{validateMessageRating(rating);}catch(e){fail(400,e.message);}return {order:raw.order,rating,data:JSON.stringify(rating)};});
  const stamp=now();await db.batch(rows.map(r=>db.prepare('INSERT INTO interactive_ratings (session_id,turn_order,valence,arousal,naturalness,target_match,rating_scale,rating_json,created_utc,received_utc) SELECT ?,?,?,?,?,?,?,?,?,? WHERE EXISTS (SELECT 1 FROM interactive_sessions WHERE session_id=? AND withdrawn_utc IS NULL) ON CONFLICT(session_id,turn_order) DO NOTHING').bind(s.session_id,r.order,r.rating.valence,r.rating.arousal,r.rating.naturalness,r.rating.target_match,r.rating.rating_scale,r.data,r.rating.created_utc,stamp,s.session_id)));
  const saved=(await db.prepare('SELECT turn_order,rating_json FROM interactive_ratings WHERE session_id=? ORDER BY turn_order').bind(s.session_id).all()).results;
  for(const r of rows)if(saved.find(x=>x.turn_order===r.order)?.rating_json!==r.data)fail(409,'A saved message rating cannot be overwritten.');
  return json({saved_count:saved.length,orders:saved.map(x=>x.turn_order)});
 }
 if(request.method==='POST'&&match[2]==='/turns'){
  const input=await body(request),limit=s.mode==='explore'?10:12;if(!Array.isArray(input.turns)||input.turns.length<1||input.turns.length>limit)fail(400,`Send 1–${limit} exchanges.`);
  const existing=await read(),merged=new Map(existing.map(t=>[t.turn_order,t.turn_json])),seen=new Set();
  const turns=input.turns.map(raw=>{
   const turn=Object.fromEntries(['order','engine','emotion','input_text','output_text','controls','audio_metrics','audio_sha256','duration_s','elapsed_s','created_utc','generation_metadata'].map(k=>[k,raw[k]]));
   if(turn.generation_metadata!==undefined&&(!turn.generation_metadata||Array.isArray(turn.generation_metadata)||typeof turn.generation_metadata!=='object'||JSON.stringify(turn.generation_metadata).length>4096))fail(400,'Invalid generation metadata.');
   try{validateConversationTurn(s,turn);if(s.mode==='explore'&&turn.controls.condition!=='preset')throw new Error('Explore uses the chosen emotion preset.');const expected=controlsFor({...turn.controls,custom:turn.controls});for(const k of ['rate','gain','pitch','voice','pitch_semitones','control_version','words_per_minute','length_scale'])if(expected[k]!==turn.controls[k])throw new Error('Voice settings do not match the selected preset.');if(JSON.stringify(expected.conditioning)!==JSON.stringify(turn.controls.conditioning))throw new Error('Native conditioning does not match the chosen emotion.');}catch(e){fail(400,e.message);}
   if(seen.has(turn.order))fail(400,'Duplicate exchange order.');seen.add(turn.order);
   const data=JSON.stringify(turn);if(merged.has(turn.order)&&merged.get(turn.order)!==data)fail(409,'A saved exchange cannot be overwritten.');merged.set(turn.order,data);return {turn,data};
  });
  if([...merged.keys()].sort((a,b)=>a-b).some((order,i)=>order!==i+1))fail(400,'Save exchanges in order.');
  const stamp=now();await db.batch([...turns.map(({turn,data})=>db.prepare('INSERT INTO interactive_turns (session_id,turn_order,engine,emotion,input_text,output_text,turn_json,created_utc,received_utc) SELECT ?,?,?,?,?,?,?,?,? WHERE EXISTS (SELECT 1 FROM interactive_sessions WHERE session_id=? AND withdrawn_utc IS NULL) ON CONFLICT(session_id,turn_order) DO NOTHING').bind(s.session_id,turn.order,turn.engine,turn.emotion,turn.input_text,turn.output_text,data,turn.created_utc,stamp,s.session_id)),db.prepare('UPDATE interactive_sessions SET updated_utc=? WHERE session_id=? AND withdrawn_utc IS NULL').bind(stamp,s.session_id)]);
  const saved=await read();for(const {turn,data} of turns)if(saved.find(t=>t.turn_order===turn.order)?.turn_json!==data)fail(409,'A simultaneous change prevented saving. Reload this conversation.');
  return json({saved_count:saved.length});
 }
 fail(405,'Method not allowed.');
}
