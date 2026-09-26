// Playback log: every play, pause, finish and seek of a voice, and each Explore transcript opening and closing, in the
// order the browser recorded it.
import {MEDIA_EVENTS,TRANSCRIPT_EVENTS} from '../playback-log.js';
export const MAX_PLAYBACK_BATCH=200;
// Far above a real session (a few events per clip). Beyond it, events are acknowledged but not stored.
export const MAX_PLAYBACK_EVENTS=20000;
const EVENT_ID=/^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/;
const number=(v,min,max)=>typeof v==='number'&&Number.isFinite(v)&&v>=min&&v<=max;
const ACTIVE={study:'SELECT 1 FROM study_sessions WHERE participant_id=? AND withdrawn_utc IS NULL',interactive:'SELECT 1 FROM interactive_sessions WHERE session_id=? AND withdrawn_utc IS NULL'};

// itemFor(order) returns the clip a Listening trial must name; interactive messages carry no clip ID.
// transcripts allows transcript openings and closings, which only Explore messages have.
export function validatePlayback(input,{fail,maxOrder,itemFor=null,transcripts=false}){
 const allowed=transcripts?[...MEDIA_EVENTS,...TRANSCRIPT_EVENTS]:MEDIA_EVENTS;
 if(!Array.isArray(input?.events)||input.events.length<1||input.events.length>MAX_PLAYBACK_BATCH)fail(400,`Send 1–${MAX_PLAYBACK_BATCH} playback events.`);
 const seen=new Set();
 return input.events.map(raw=>{
  const e=Object.fromEntries(['event_id','seq','event','item_order','item_id','position_s','duration_s','playback_rate','autoplay','client_utc'].map(k=>[k,raw?.[k]]));
  if(!EVENT_ID.test(e.event_id||'')||seen.has(e.event_id)||!Number.isInteger(e.seq)||e.seq<1||e.seq>1000000||!allowed.includes(e.event)
   ||!Number.isInteger(e.item_order)||e.item_order<1||e.item_order>maxOrder||!number(e.position_s,0,86400)||!(e.duration_s===null||number(e.duration_s,0,86400))
   ||!number(e.playback_rate,0,16)||typeof e.autoplay!=='boolean'||typeof e.client_utc!=='string'||e.client_utc.length>30||!Number.isFinite(Date.parse(e.client_utc)))fail(400,'Invalid playback event.');
  seen.add(e.event_id);
  if(itemFor){if(e.item_id!==itemFor(e.item_order))fail(400,'A playback event does not match the assigned clip.');}
  else if(e.item_id!==null&&e.item_id!==undefined)fail(400,'Invalid playback event.');
  return {...e,item_id:itemFor?e.item_id:null};
 });
}

const count=async(db,kind,id)=>(await db.prepare('SELECT COUNT(*) AS n FROM playback_events WHERE session_kind=? AND session_id=?').bind(kind,id).first()).n;

// Retries are harmless: an event already stored is skipped, and every received event is acknowledged so the browser can drop it.
export async function savePlayback(db,kind,sessionId,events,received){
 const room=Math.max(0,MAX_PLAYBACK_EVENTS-await count(db,kind,sessionId)),kept=events.slice(0,room);
 if(kept.length)await db.batch(kept.map(e=>db.prepare(`INSERT INTO playback_events (session_kind,session_id,event_id,seq,event,item_order,item_id,position_s,duration_s,playback_rate,autoplay,client_utc,received_utc) SELECT ?,?,?,?,?,?,?,?,?,?,?,?,? WHERE EXISTS (${ACTIVE[kind]}) ON CONFLICT(session_kind,session_id,event_id) DO NOTHING`)
  .bind(kind,sessionId,e.event_id,e.seq,e.event,e.item_order,e.item_id,e.position_s,e.duration_s,e.playback_rate,Number(e.autoplay),e.client_utc,received,sessionId)));
 return {received_event_ids:events.map(e=>e.event_id),stored_count:await count(db,kind,sessionId)};
}

export const deletePlayback=(db,kind,sessionId)=>db.prepare('DELETE FROM playback_events WHERE session_kind=? AND session_id=?').bind(kind,sessionId);
