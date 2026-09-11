import {validateNickname} from '../participant.js';
import {audioDownload} from './audio.js';
import {interactiveApi,explorationCSV} from './interactive.js';
import manifest from '../public/study/manifest.json' with { type: 'json' };
import previousManifest from '../public/study/manifest-v4.json' with { type: 'json' };
const manifests=new Map([manifest,previousManifest].map(m=>[m.study_version,m]));
function trialCount(version){return manifests.get(version)?.trials_per_session ?? (version.includes('calibrated-v2')?30:26);}
import { makeTrials, rowsCSV, RATING_SCALE } from '../study-session.js';
import { database, readSession, readResponses } from './db.js';

export const COLLECTION_VERSION = 'echo-collection-sqlite-20260907-v5';
const ID = /^(?:P|TEST)-[A-F0-9]{8,32}$/;
class RequestError extends Error { constructor(status, message) { super(message); this.status = status; } }
const fail = (status, message) => { throw new RequestError(status, message); };
const now = () => new Date().toISOString();
const json = (data, status = 200) => new Response(JSON.stringify(data), { status, headers: {'Content-Type':'application/json', 'Cache-Control':'no-store', 'X-Content-Type-Options':'nosniff'} });
function integer(v, min, max) { return Number.isInteger(v) && v >= min && v <= max; }
function date(v) { return typeof v === 'string' && v.length <= 30 && Number.isFinite(Date.parse(v)); }
async function body(request) {
  if (!request.headers.get('content-type')?.startsWith('application/json')) fail(415, 'Send JSON.');
  const reader = request.body?.getReader(); if (!reader) fail(400, 'Missing request body.');
  const chunks = []; let bytes = 0;
  for (;;) { const {done,value} = await reader.read(); if (done) break; bytes += value.byteLength; if (bytes > 65536) { await reader.cancel(); fail(413,'Request is too large.'); } chunks.push(value); }
  const all = new Uint8Array(bytes); let offset=0; for (const c of chunks) { all.set(c,offset); offset+=c.length; }
  try { const result = JSON.parse(new TextDecoder().decode(all)); if (!result || Array.isArray(result) || typeof result !== 'object') fail(400,'Invalid request.'); return result; }
  catch { fail(400, 'Invalid JSON.'); }
}
async function tokenHash(request) {
  const token = request.headers.get('authorization')?.match(/^Bearer ([a-f0-9]{64})$/)?.[1];
  if (!token) fail(401,'This session needs its original browser credentials.');
  const hash = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(token));
  return Array.from(new Uint8Array(hash), x=>x.toString(16).padStart(2,'0')).join('');
}
async function owned(request, db, id) {
  if (!ID.test(id)) fail(400,'Invalid participant code.');
  const hash = await tokenHash(request), s = await readSession(db,id);
  if (!s || s.token_hash !== hash) fail(403,'Session access denied.');
  return s;
}
function researcher(request, env) {
  // The Node server validates its private session cookie before calling this module.
  // No inbound identity header is used as evidence of researcher access.
  if (env.RESEARCHER_AUTHORIZED !== true) fail(401, 'Sign in with the researcher password.');
}

function sessionMetadata(input) {
  if (!ID.test(input.participant_id || '')) fail(400,'Invalid participant code.');
  if (!manifests.has(input.study_version) || input.collection_version !== COLLECTION_VERSION) fail(409,'This study version changed. Reload the page.');
  if (!['human_response','technical_test'].includes(input.record_type) || input.participant_id.startsWith('TEST-') !== (input.record_type === 'technical_test')) fail(400,'Invalid session type.');
  if (!integer(input.group,0,15) || !integer(input.seed,0,4294967295)) fail(400,'Invalid allocation.');
  if (input.consent !== true || !date(input.consent_utc)) fail(400,'Consent to server storage is required.');
  const e=input.eligibility;
  if (!e || !['comfortable_english','headphones','previously_used_studio'].every(k=>typeof e[k]==='boolean')) fail(400,'Complete the listening eligibility questions.');
  if (input.record_type==='human_response' && (!e.comfortable_english || !e.headphones)) fail(400,'Confirm English comprehension and headphone use.');
  try{input.nickname=validateNickname(input.nickname);}catch(e){fail(400,e.message);}
  if(input.rating_scale!==RATING_SCALE)fail(409,'Reload the current rating scale.');
  return input;
}
function sameSession(s,input) {
  return s.nickname===input.nickname && s.rating_scale===input.rating_scale && s.study_version===input.study_version && s.collection_version===input.collection_version && s.record_type===input.record_type && s.group_number===input.group+1 && s.seed===input.seed &&
    ['comfortable_english','headphones','previously_used_studio'].every(k=>s[k]===Number(input.eligibility[k]));
}
function csvRow(s,r) {
  return {study_version:s.study_version, collection_version:s.collection_version, rating_scale:s.rating_scale, nickname:s.nickname, record_type:s.record_type, participant_id:s.participant_id, group:s.group_number, seed:s.seed, order:r.trial_order,
    item_id:r.item_id, audio_sha256:manifests.get(s.study_version)?.items.find(i=>i.item_id===r.item_id)?.sha256 || '', block_id:r.block_id, valence:r.valence, arousal:r.arousal, naturalness:r.naturalness, target_match:r.target_match,
    play_count:r.play_count, completed_audio:Boolean(r.completed_audio), elapsed_s:r.elapsed_s.toFixed(2), created_utc:r.created_utc,
    comfortable_english:Boolean(s.comfortable_english), headphones:Boolean(s.headphones), previously_used_studio:Boolean(s.previously_used_studio)};
}
async function snapshot(db,s) {
  if(s.withdrawn_utc) fail(410,'This contribution was deleted.');
  const rows=await readResponses(db,s.participant_id), complete=rows.filter(r=>r.target_match!==null);
  return {participant_id:s.participant_id, nickname:s.nickname, rating_scale:s.rating_scale, group:s.group_number-1, seed:s.seed, study_version:s.study_version, collection_version:s.collection_version, record_type:s.record_type,
    eligibility:Object.fromEntries(['comfortable_english','headphones','previously_used_studio'].map(k=>[k,Boolean(s[k])])),
    rows:complete.map(r=>csvRow(s,r)), pending:rows.find(r=>r.target_match===null) || null, saved_count:complete.length, trials_per_session:trialCount(s.study_version), complete:complete.length===trialCount(s.study_version)};
}
function validateRows(input,s,existing) {
  const assigned=manifests.get(s.study_version);
  if(!assigned||s.collection_version!==COLLECTION_VERSION)fail(409,'This session belongs to an earlier frozen study. Download or delete it; start a new session for the calibrated study.');
  if (!Array.isArray(input.rows) || input.rows.length < 1 || input.rows.length > assigned.trials_per_session) fail(400,'Send responses within this session’s assigned clip count.');
  const trials=makeTrials(assigned,s.group_number-1,s.seed), seen=new Set(), merged=new Map(existing.map(r=>[r.trial_order,r]));
  const result=input.rows.map(r=>{
    if (!integer(r.order,1,assigned.trials_per_session) || seen.has(r.order)) fail(400,'Invalid or duplicate trial order.'); seen.add(r.order);
    const t=trials[r.order-1];
    if (r.item_id!==t.item_id || r.block_id!==t.block_id) fail(400,'Clip does not match the assigned trial.');
    if (!['valence','arousal'].every(k=>typeof r[k]==='number' && Number.isFinite(r[k]) && r[k]>=-1 && r[k]<=1 && Math.abs(r[k]*100-Math.round(r[k]*100))<1e-6)) fail(400,'Invalid emotional rating.');
    if (!integer(r.naturalness,1,5) || !(r.target_match===null || (typeof r.target_match==='number' && r.target_match>=1 && r.target_match<=5 && Number.isInteger(r.target_match*2)))) fail(400,'Invalid rating.');
    if (!integer(r.play_count,0,10000) || typeof r.completed_audio!=='boolean' || typeof r.elapsed_s!=='number' || !Number.isFinite(r.elapsed_s) || r.elapsed_s<0 || r.elapsed_s>31536000 || !date(r.created_utc)) fail(400,'Invalid playback information.');
    if (s.record_type==='human_response' && (!r.completed_audio || r.play_count<1)) fail(400,'Listen to the complete clip before rating.');
    const old=merged.get(r.order);
    if (old && (['item_id','block_id','valence','arousal','naturalness'].some(k=>old[k]!==r[k]) || (old.target_match!==null && r.target_match!==null && old.target_match!==r.target_match))) fail(409,'A saved rating is locked and cannot be replaced.');
    merged.set(r.order,{...r,target_match:old?.target_match ?? r.target_match}); return r;
  });
  const all=[...merged.entries()].sort((a,b)=>a[0]-b[0]);
  if (all.some(([order,r],i)=>order!==i+1 || (i<all.length-1 && r.target_match===null))) fail(400,'Complete each assigned clip in order.');
  return result;
}
const insertResponse = `INSERT INTO study_responses (participant_id,trial_order,item_id,block_id,valence,arousal,naturalness,target_match,play_count,completed_audio,elapsed_s,created_utc,received_utc,completed_utc)
 SELECT ?,?,?,?,?,?,?,?,?,?,?,?,?,? WHERE EXISTS (SELECT 1 FROM study_sessions WHERE participant_id = ? AND withdrawn_utc IS NULL)
 ON CONFLICT(participant_id,trial_order) DO UPDATE SET target_match=COALESCE(study_responses.target_match,excluded.target_match),
 play_count=CASE WHEN study_responses.target_match IS NULL THEN excluded.play_count ELSE study_responses.play_count END,
 elapsed_s=CASE WHEN study_responses.target_match IS NULL THEN excluded.elapsed_s ELSE study_responses.elapsed_s END,
 created_utc=CASE WHEN study_responses.target_match IS NULL THEN excluded.created_utc ELSE study_responses.created_utc END,
 completed_utc=COALESCE(study_responses.completed_utc,excluded.completed_utc)
 WHERE study_responses.item_id=excluded.item_id AND study_responses.block_id=excluded.block_id AND study_responses.valence=excluded.valence
 AND study_responses.arousal=excluded.arousal AND study_responses.naturalness=excluded.naturalness
 AND (study_responses.target_match IS NULL OR excluded.target_match IS NULL OR study_responses.target_match=excluded.target_match)`;

async function api(request,env,url) {
  const db=database(env), path=url.pathname, method=request.method;
  if (!['GET','HEAD'].includes(method)) {
    const origin=request.headers.get('origin');
    if (!origin || origin!==url.origin || request.headers.get('sec-fetch-site')==='cross-site') fail(403,'Only this website can submit responses.');
  }
  if(path.startsWith('/api/interactive/'))return interactiveApi(request,url,{db,body,tokenHash,fail,json,now,audioBucket:env.AUDIO});
  if(path==='/api/study/status' && method==='GET') {
    await db.prepare('SELECT participant_id FROM study_sessions LIMIT 1').first();
    return json({available:true,study_version:manifest.study_version,collection_version:COLLECTION_VERSION});
  }
  if(path==='/api/study/sessions' && method==='POST') {
    const input=sessionMetadata(await body(request)), hash=await tokenHash(request), timestamp=now();
    await db.prepare(`INSERT INTO study_sessions (participant_id,token_hash,study_version,collection_version,record_type,group_number,seed,comfortable_english,headphones,previously_used_studio,consent_utc,received_utc,updated_utc,nickname,rating_scale)
     VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(participant_id) DO NOTHING`).bind(input.participant_id,hash,input.study_version,input.collection_version,input.record_type,input.group+1,input.seed,Number(input.eligibility.comfortable_english),Number(input.eligibility.headphones),Number(input.eligibility.previously_used_studio),input.consent_utc,timestamp,timestamp,input.nickname,input.rating_scale).run();
    const s=await owned(request,db,input.participant_id);
    if(s.withdrawn_utc)fail(410,'This contribution was deleted.');
    if(!sameSession(s,input)) fail(409,'Session metadata cannot be changed.');
    return json(await snapshot(db,s));
  }
  const match=path.match(/^\/api\/study\/sessions\/([^/]+)(\/responses)?$/);
  if(match) {
    let s=await owned(request,db,match[1]);
    if(method==='DELETE' && !match[2]) {
      await db.batch([db.prepare('UPDATE study_sessions SET withdrawn_utc=COALESCE(withdrawn_utc,?), nickname=?, updated_utc=? WHERE participant_id=?').bind(now(),'',now(),s.participant_id), db.prepare('DELETE FROM study_responses WHERE participant_id=?').bind(s.participant_id)]);
      return json({withdrawn:true});
    }
    if(s.withdrawn_utc) fail(410,'This contribution was deleted.');
    if(method==='GET' && !match[2]) return json(await snapshot(db,s));
    if(method==='POST' && match[2]) {
      const rows=validateRows(await body(request),s,await readResponses(db,s.participant_id)), timestamp=now();
      await db.batch([...rows.map(r=>db.prepare(insertResponse).bind(s.participant_id,r.order,r.item_id,r.block_id,r.valence,r.arousal,r.naturalness,r.target_match,r.play_count,Number(r.completed_audio),r.elapsed_s,r.created_utc,timestamp,r.target_match===null?null:timestamp,s.participant_id)),
        db.prepare(`UPDATE study_sessions SET updated_utc=?, completed_utc=CASE WHEN (SELECT COUNT(*) FROM study_responses WHERE participant_id=? AND target_match IS NOT NULL)=${trialCount(s.study_version)} THEN COALESCE(completed_utc,?) ELSE completed_utc END WHERE participant_id=? AND withdrawn_utc IS NULL`).bind(timestamp,s.participant_id,timestamp,s.participant_id)]);
      s=await readSession(db,s.participant_id);
      const saved=await readResponses(db,s.participant_id);
      for(const row of rows) {
        const actual=saved.find(r=>r.trial_order===row.order);
        if (!actual || ['item_id','block_id','valence','arousal','naturalness'].some(k=>actual[k]!==row[k]) || (row.target_match!==null && row.target_match!==actual.target_match)) fail(409,'A simultaneous change prevented saving. Reload this session.');
      }
      return json(await snapshot(db,s));
    }
  }
  if(path.startsWith('/api/research/')) {
    researcher(request,env); if(method!=='GET') fail(405,'Method not allowed.');
    const audioRoute=path.match(/^\/api\/research\/interactive\/audio\/(X-[A-F0-9]{32})\/([1-9][0-9]?)$/);
    if(audioRoute)return audioDownload(db,env.AUDIO,audioRoute[1],Number(audioRoute[2]),fail);
    if(path==='/api/research/summary') {
      const counts=(await db.prepare(`SELECT s.record_type, s.group_number, COUNT(*) AS started,
        SUM(CASE WHEN s.completed_utc IS NOT NULL THEN 1 ELSE 0 END) AS completed,
        SUM(CASE WHEN s.completed_utc IS NOT NULL AND s.previously_used_studio=0 AND s.comfortable_english=1 AND s.headphones=1 THEN 1 ELSE 0 END) AS eligible,
        SUM((SELECT COUNT(*) FROM study_responses r WHERE r.participant_id=s.participant_id AND r.target_match IS NOT NULL)) AS responses
        FROM study_sessions s WHERE s.withdrawn_utc IS NULL AND s.collection_version=? AND s.study_version=? GROUP BY s.record_type,s.group_number ORDER BY s.record_type,s.group_number`).bind(COLLECTION_VERSION,manifest.study_version).all()).results;
      const sessions=(await db.prepare(`SELECT s.participant_id,s.study_version,s.nickname,s.collection_version,s.rating_scale,s.record_type,s.group_number,s.received_utc,s.updated_utc,s.completed_utc,s.previously_used_studio,
        (SELECT COUNT(*) FROM study_responses r WHERE r.participant_id=s.participant_id AND r.target_match IS NOT NULL) AS saved_count
        FROM study_sessions s WHERE s.withdrawn_utc IS NULL ORDER BY s.received_utc DESC LIMIT 200`).all()).results;
      return json({study_version:manifest.study_version,collection_version:COLLECTION_VERSION,trials_per_session:manifest.trials_per_session,groups:counts,sessions:sessions.map(s=>({...s,trials_per_session:trialCount(s.study_version)})),session_list_limit:200});
    }
    if(path==='/api/research/interactive') {
      const sessions=(await db.prepare(`SELECT s.session_id,s.nickname,s.mode,s.engine,s.record_type,s.updated_utc,(SELECT COUNT(*) FROM interactive_turns t WHERE t.session_id=s.session_id) AS saved_count,(SELECT COUNT(*) FROM interactive_ratings r WHERE r.session_id=s.session_id) AS rated_count,(SELECT COUNT(*) FROM interactive_audio a WHERE a.session_id=s.session_id) AS archived_count FROM interactive_sessions s WHERE s.withdrawn_utc IS NULL ORDER BY s.updated_utc DESC LIMIT 200`).all()).results;
      return json({sessions});
    }
    if(path==='/api/research/diagnostics.json'){const rows=(await db.prepare('SELECT a.session_id,s.mode,s.record_type,a.event_json,a.received_utc FROM generation_attempts a JOIN interactive_sessions s ON s.session_id=a.session_id WHERE s.withdrawn_utc IS NULL ORDER BY a.received_utc').all()).results;return json({scope:'TTS requests only; excludes dialogue generation failures, disconnected unsynchronised clients and infrastructure-wide monitoring. Times include connection, queue, download and processing.',attempts:rows.map(r=>({...r,event_json:undefined,...JSON.parse(r.event_json)}))});}
    if(path==='/api/research/interactive.csv') {
      const rows=(await db.prepare(`SELECT s.session_id,s.nickname,s.mode,s.record_type,t.turn_order,t.engine,t.emotion,t.input_text,t.output_text,t.created_utc,t.turn_json,r.rating_json,a.stored_utc AS audio_stored_utc FROM interactive_sessions s JOIN interactive_turns t ON t.session_id=s.session_id LEFT JOIN interactive_ratings r ON r.session_id=t.session_id AND r.turn_order=t.turn_order LEFT JOIN interactive_audio a ON a.session_id=t.session_id AND a.turn_order=t.turn_order WHERE s.withdrawn_utc IS NULL ORDER BY s.session_id,t.turn_order`).all()).results;
      return new Response(explorationCSV(rows),{headers:{'Content-Type':'text/csv;charset=utf-8','Content-Disposition':'attachment; filename="echo-exploration.csv"','Cache-Control':'no-store'}});
    }
    if(path==='/api/research/responses.csv') {
      const type=url.searchParams.get('type')==='technical'?'technical_test':'human_response';
      const rows=(await db.prepare(`SELECT s.*,r.* FROM study_sessions s JOIN study_responses r ON r.participant_id=s.participant_id
        WHERE s.withdrawn_utc IS NULL AND s.record_type=? AND r.target_match IS NOT NULL ORDER BY s.participant_id,r.trial_order`).bind(type).all()).results;
      return new Response(rowsCSV(rows.map(r=>csvRow(r,r))),{headers:{'Content-Type':'text/csv;charset=utf-8','Content-Disposition':`attachment; filename="echo-${type}-${now().slice(0,10)}.csv"`,'Cache-Control':'no-store','X-Content-Type-Options':'nosniff'}});
    }
  }
  fail(404,'Endpoint not found.');
}

export default {
  async fetch(request,env,ctx) {
    const url=new URL(request.url);
    try {
      if(url.pathname.startsWith('/api/')) return await api(request,env,url);
      return json({error:'Endpoint not found.'},404);
    } catch(error) {
      if (!(error instanceof RequestError)) console.error('Study request failed:',error.message);
      return json({error:error instanceof RequestError ? error.message : 'The study could not save to its database. Your browser copy is retained. Please retry.'},error.status || 503);
    }
  }
};
