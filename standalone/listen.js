import {makeTrials,validateRating,rowsCSV} from './study-session.js';
import {StudySync,newSessionToken,COLLECTION_VERSION} from './study-sync.js';
import {readNickname,rememberNickname} from './participant.js';
import {listenerId} from './listener.js';
import {trackPlayback} from './playback-log.js';
import {RATING_SCALE} from './study-session.js';
import {targetName} from './circumplex.js';
const $=id=>document.getElementById(id),query=new URLSearchParams(location.search),test=query.get('test')==='1';
const storageKey=`echo-voice-study-v4${test?'-technical':''}`;let manifest,currentManifest,session,trials,heard=false,playCount=0,started=0,previousElapsed=0,touched=new Set(),locked=null,storageAvailable=true;
let syncClient=null,lastSyncState='saving';
// A playback event belongs to the clip the audio element was loading when it fired, not to the trial shown on screen.
let pendingTrial=null,activeTrial=null;
$('test-banner').hidden=!test;$('technical-fill').hidden=!test;
function error(message){$('study-error').textContent=message;$('study-error').hidden=!message;}
function persist(){try{localStorage.setItem(storageKey,JSON.stringify(session));}catch{storageAvailable=false;$('study-status').textContent='Browser backup is unavailable. Keep this tab open until the server confirms your responses.';}}
function save(){persist();if(syncClient)void syncClient.sync();}
function syncStatus({state,saved,message}){
 lastSyncState=state;persist();$('sync-panel').hidden=false;$('retry-save').hidden=state==='saved'||state==='saving';
 const total=session?.rows.length || 0;
 $('sync-status').textContent=state==='saved'?`Received by the researcher: ${saved} of ${manifest?.trials_per_session||45} responses.`:state==='saving'?`Saving to the study database… ${saved} of ${manifest?.trials_per_session||45} received.`:state==='conflict'?message:`Waiting to send ${Math.max(0,total-saved)} completed responses. Your browser copy is retained; reconnect and retry.`;
 $('sync-status').dataset.state=state;
 $('complete-message').textContent=state==='saved'&&saved===manifest.trials_per_session?'All responses have been received. You do not need to email a file. You can download a copy for your records.':'Your listening is complete, but the database has not confirmed all responses yet. Keep this page open and retry, or download your backup.';
}
function connectSync(){syncClient=new StudySync({session,trials,onStatus:syncStatus});}
function panels(name){for(const id of ['setup','resume','trial','complete'])$(id).hidden=id!==name;}
function download(){const blob=new Blob([rowsCSV(session.rows)],{type:'text/csv;charset=utf-8'}),url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download=`echo-${test?'TECHNICAL-TEST-':''}${session.participant_id}-${session.rows.length}responses.csv`;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
function showTrial(){
 error('');$('session-actions').hidden=false;
 if(session.rows.length===trials.length){panels('complete');$('study-audio').pause();$('complete-code').textContent=`${session.nickname} · ${session.participant_id} · ${session.rows.length} responses${test?' · TECHNICAL TEST ONLY':''}`;return;}
 panels('trial');const i=session.rows.length,t=trials[i],item=manifest.items.find(x=>x.item_id===t.item_id);if(!item)throw new Error('This clip is missing from the study.');
 heard=false;playCount=0;locked=null;touched=new Set();started=performance.now();previousElapsed=0;$('rating-form').reset();$('perceived').disabled=true;$('target-rating').hidden=true;$('reveal-target').hidden=false;
 $('target-match-value').textContent='Not rated';$('target-match').value='3';
 $('valence-value').textContent='Not rated';$('arousal-value').textContent='Not rated';$('clip-title').textContent=`Clip ${i+1} of ${trials.length}`;$('participant-code').textContent=`${session.nickname} · ${session.participant_id}`;$('study-progress').max=trials.length;$('study-progress').value=i;
 $('break-reminder').hidden=!(i>0&&i%15===0);
 $('play-instruction').textContent='Listen to the whole clip before rating it. You may replay it.';pendingTrial={item_order:i+1,item_id:t.item_id};$('study-audio').src=item.audio;$('study-audio').playbackRate=1;
 const pending=session.current;
 if(pending?.index===i){
  locked={...pending.locked};heard=pending.heard;playCount=pending.playCount;previousElapsed=pending.elapsed_s;
  for(const k of ['valence','arousal']){$(k).value=String(locked[k]*100);$(k+'-value').textContent=String(Math.round(locked[k]*100));}
  document.querySelector(`input[name=naturalness][value="${locked.naturalness}"]`).checked=true;
  $('perceived').disabled=true;$('reveal-target').hidden=true;$('target-rating').hidden=false;
  $('intended-emotion').textContent=`${targetName(t.target)} · ${t.target.arousal>0?'active':'passive'}, ${t.target.valence>0?'positive':'negative'}`;
  $('play-instruction').textContent='Your first ratings are saved and locked. Complete the target-match rating.';
 }
 $('clip-title').focus();
}
function perception(){
 if(!heard&&!test)throw new Error('Please listen to the whole clip first.');
 if(!touched.has('valence')||!touched.has('arousal'))throw new Error('Rate both emotional dimensions. Use the neutral buttons if your rating is zero.');
 const r={valence:Number($('valence').value)/100,arousal:Number($('arousal').value)/100,naturalness:Number(document.querySelector('input[name=naturalness]:checked')?.value),target_match:1};validateRating(r);delete r.target_match;return r;
}
function reveal(){try{error('');locked=perception();session.current={index:session.rows.length,locked,heard,playCount,elapsed_s:previousElapsed+(performance.now()-started)/1000,created_utc:new Date().toISOString()};save();$('perceived').disabled=true;$('reveal-target').hidden=true;$('target-rating').hidden=false;const t=trials[session.rows.length];$('intended-emotion').textContent=`${targetName(t.target)} · ${t.target.arousal>0?'active':'passive'}, ${t.target.valence>0?'positive':'negative'}`;}catch(e){error(e.message);}}
function record(){
 if(!locked)throw new Error('Save your perception ratings first.');
 if(!touched.has('target-match'))throw new Error('Rate the emotion match. Use the midpoint button if your rating is 3.');
 const rating={...locked,target_match:Number($('target-match').value)};validateRating(rating);
 const i=session.rows.length,t=trials[i];session.rows.push({study_version:manifest.study_version,collection_version:COLLECTION_VERSION,rating_scale:RATING_SCALE,nickname:session.nickname,record_type:test?'technical_test':'human_response',participant_id:session.participant_id,group:session.group+1,seed:session.seed,order:i+1,item_id:t.item_id,audio_sha256:manifest.items.find(j=>j.item_id===t.item_id).sha256,block_id:t.block_id,...rating,play_count:playCount,completed_audio:heard,elapsed_s:(previousElapsed+(performance.now()-started)/1000).toFixed(2),created_utc:new Date().toISOString(),...session.eligibility});session.current=null;save();showTrial();
}
$('study-audio').addEventListener('play',()=>playCount++);
$('study-audio').addEventListener('ended',()=>{if($('study-audio').playbackRate!==1){error('Use normal playback speed (1×) and listen again.');return;}heard=true;if(!locked)$('perceived').disabled=false;$('play-instruction').textContent='Clip heard. Rate the voice below; you can replay it.';});
$('study-audio').addEventListener('error',()=>error('This audio could not load. Check your connection and reload to resume the same clip.'));
$('study-audio').addEventListener('loadstart',()=>{activeTrial=pendingTrial;});
trackPlayback($('study-audio'),()=>activeTrial,event=>{if(!syncClient)return;syncClient.playback(event);persist();});
for(const key of ['valence','arousal']){
 const update=()=>{touched.add(key);$(key+'-value').textContent=String(Number($(key).value));};$(key).addEventListener('input',update);$('neutral-'+key).addEventListener('click',()=>{$(key).value='0';update();});
}
$('reveal-target').addEventListener('click',reveal);
$('rating-form').addEventListener('submit',e=>{e.preventDefault();try{record();}catch(e){error(e.message);}});
$('start-form').addEventListener('submit',e=>{
 e.preventDefault();const random=crypto.getRandomValues(new Uint32Array(2)),requested=query.get('g'),group=requested?Number(requested)-1:random[0]%manifest.groups.length;
 try{
  if(test){/* Technical sessions remain marked even when exercising the ordinary form. */}
  session={nickname:rememberNickname($('study-nickname').value),listener_id:listenerId(),collection_version:COLLECTION_VERSION,rating_scale:RATING_SCALE,study_version:manifest.study_version,participant_id:(test?'TEST-':'P-')+crypto.randomUUID().replaceAll('-','').toUpperCase(),seed:random[1],group,rows:[],eligibility:{comfortable_english:$('english').checked,headphones:$('headphones').checked,previously_used_studio:$('previous-studio').checked||wasExposed()},consent_utc:new Date().toISOString(),record_type:test?'technical_test':'human_response',remote:{token:newSessionToken(),consent_utc:new Date().toISOString(),saved_count:0}};
  trials=makeTrials(manifest,group,session.seed);connectSync();save();showTrial();
 }catch(e){error(e.message);}
});
$('resume-button').addEventListener('click',async()=>{
 try{
  error('');if(!session.remote){if(!$('transfer-consent').checked)throw new Error('Agree to server storage before transferring your existing responses.');session.remote={token:newSessionToken(),consent_utc:new Date().toISOString(),saved_count:0};if(session.current&&!session.current.created_utc)session.current.created_utc=new Date().toISOString();}
  session.listener_id||=listenerId();trials=makeTrials(manifest,session.group,session.seed);connectSync();persist();$('resume-button').disabled=true;
  try{await syncClient.restore();}catch(e){if([400,401,403,409,410].includes(e.status))throw e;}
  save();showTrial();
 }catch(e){error(e.message);}finally{$('resume-button').disabled=false;}
});
$('new-session').addEventListener('click',()=>{download();if(lastSyncState!=='saved'||session.remote.saved_count!==manifest.trials_per_session){error('Wait until all responses are received, or use Delete my ratings to withdraw this session.');return;}syncClient.stopped=true;syncClient=null;try{localStorage.removeItem(storageKey);}catch{}session=null;trials=null;manifest=currentManifest;$('study-status').textContent='45 clips · 9 synthesis systems';$('start-form').reset();$('session-actions').hidden=true;$('sync-panel').hidden=true;panels('setup');});
$('download-partial').addEventListener('click',download);$('download-complete').addEventListener('click',download);
$('retry-save').addEventListener('click',()=>void syncClient?.sync());
window.addEventListener('online',()=>void syncClient?.sync());
const retryTimer=setInterval(()=>{if(syncClient?.dirty&&lastSyncState!=='conflict')void syncClient.sync();},15000);
window.addEventListener('pagehide',()=>clearInterval(retryTimer),{once:true});
$('withdraw-show').addEventListener('click',()=>{$('withdraw-confirm').hidden=false;});
$('withdraw-cancel').addEventListener('click',()=>{$('withdraw-confirm').hidden=true;});
$('withdraw-delete').addEventListener('click',async()=>{try{$('withdraw-delete').disabled=true;await syncClient.withdraw();try{localStorage.removeItem(storageKey);}catch{}syncClient=null;session=null;trials=null;manifest=currentManifest;$('study-status').textContent='45 clips · 9 synthesis systems';$('session-actions').hidden=true;$('sync-panel').hidden=true;$('withdraw-confirm').hidden=true;panels('setup');$('start-form').reset();$('study-status').textContent='Your ratings have been deleted. Thank you for your time.';}catch(e){error('Deletion was not confirmed. Keep this page and retry. '+e.message);}finally{$('withdraw-delete').disabled=false;}});
$('technical-fill').addEventListener('click',()=>{if(!test)return;$('perceived').disabled=false;touched=new Set(['valence','arousal']);$('valence').value='0';$('arousal').value='0';document.querySelector('input[name=naturalness][value="3"]').checked=true;reveal();$('target-match').value='3';touched.add('target-match');record();});
async function init(){try{
 const response=await fetch('/study/manifest.json');if(!response.ok)throw new Error('The study audio is not available yet. Please return when the researcher opens recruitment.');manifest=await response.json();currentManifest=manifest;
 $('study-status').textContent=`${manifest.trials_per_session} clips · 9 synthesis systems · ${manifest.study_version}`;
 try{const raw=localStorage.getItem(storageKey);if(raw)session=JSON.parse(raw);}catch{session=null;storageAvailable=false;}
 if(session?.study_version==='echo-user-voice-20260907-nine-v4'&&session.collection_version===COLLECTION_VERSION&&session.record_type===(test?'technical_test':'human_response')){const previous=await fetch('/study/manifest-v4.json');if(!previous.ok)throw new Error('The saved study version could not load. Keep this browser data and retry.');manifest=await previous.json();$('study-status').textContent='Resuming your earlier 27-clip study. Its allocation and ratings are preserved.';}
 if(session?.study_version===manifest.study_version&&session.collection_version===COLLECTION_VERSION&&session.record_type===(test?'technical_test':'human_response')){panels('resume');$('resume-description').textContent=`${session.rows.length} of ${manifest?.trials_per_session||45} responses saved in this browser. Continue with participant code ${session.participant_id}.`;$('transfer-notice').hidden=Boolean(session.remote);}
 else panels('setup');
 $('study-nickname').value=readNickname();$('previous-studio').checked=wasExposed();
 if(test&&!session){$('study-nickname').value=readNickname()||'technical_demo';$('consent').parentElement.hidden=true;$('english').parentElement.hidden=true;$('headphones').parentElement.hidden=true;$('consent').required=false;$('english').required=false;$('headphones').required=false;$('start-form').querySelector('button').textContent='Begin technical test';}
 if(!storageAvailable)$('study-status').textContent+=' · local saving unavailable';
}catch(e){error(e.message);$('study-status').textContent='Study unavailable.';}}
if(!document.getElementById('studio')){const u=new URL(location.href);u.pathname='/';u.searchParams.set('mode','listening');location.replace(u);}else init();

function wasExposed(){try{return localStorage.getItem('echo-studio-exposed')==='1';}catch{return false;}}
$('target-match').addEventListener('input',()=>{touched.add('target-match');$('target-match-value').textContent=Number($('target-match').value).toFixed(1)+' / 5';});
$('moderate-match').addEventListener('click',()=>{$('target-match').value='3';touched.add('target-match');$('target-match-value').textContent='3.0 / 5';});
$('study-nickname').addEventListener('input',()=>$('study-nickname').setCustomValidity(''));
