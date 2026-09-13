import {TEST_ENGINES,EXPLORE_ENGINES} from './engine-catalog.js';
import {messageRatingForm,refreshMessageRatings} from './message-rating-ui.js';
import {interactivePending} from './message-rating.js';
import {RemoteSpeechClient} from './remote-speech.js';
import {ENGINES,controlsFor,validateText} from './voice-controls.js';
import {QUADRANTS} from './circumplex.js';
import {requestReplyWhenReady,checkDialogue} from './dialogue-client.js';
import {NeuralClient} from './neural-client.js';
import {hashAudio} from './audio-utils.js';
import {readNickname,rememberNickname,validateNickname,nicknameAvailable,NICKNAME_TAKEN,MAX_EXCHANGES} from './participant.js';
import {createInteractiveSession,InteractiveSync,loadOutbox} from './interactive-sync.js';
import {listenerId} from './listener.js';
import {trackPlayback,trackTranscript} from './playback-log.js';
import {GENERATION_METADATA_VERSION,seconds,visibilityWatch,deviceContext} from './generation-timing.js';
const $=id=>document.getElementById(id),neural=new NeuralClient();
const remote=new RemoteSpeechClient();
let listeningLoaded=false,listeningLoading=false;
let mode='listening',busy=false,job=0,ticker,started,phase='',records=[],lastLine=null,lastComparedEngine=null,chat=null,lineSession=null,replyRequest=null;
const syncs=new Map(),requestedEngines=new Set();
function selection(){return {emotion:document.querySelector('input[name=emotion]:checked').value,intensity:1,engine:mode==='explore'?(chat?.engine||$('chat-engine').value):$('engine').value,condition:mode==='explore'?'preset':$('condition').value,custom:{rate:Number($('custom-rate').value)/100,gain:Number($('custom-gain').value)/100,pitch:Number($('custom-pitch').value)}};}
for(const [id,engines] of [['engine',TEST_ENGINES],['chat-engine',EXPLORE_ENGINES]])$(id).replaceChildren(...engines.map(e=>new Option(ENGINES[e].name,e)));
$('compare-actions').querySelectorAll('[data-compare-engine]').forEach(b=>b.remove());
for(const e of TEST_ENGINES){const button=document.createElement('button');button.type='button';button.className='secondary';button.dataset.compareEngine=e;button.textContent='Compare '+ENGINES[e].name;$('compare-actions').append(button);}
function update(){
 const s=selection(),engine=ENGINES[s.engine];
 for(const option of $('condition').options)option.disabled=s.engine!=='kokoro'&&!['preset','neutral'].includes(option.value);
 if($('condition').selectedOptions[0].disabled){$('condition').value='preset';s.condition='preset';}
 $('pitch-option').disabled=!engine.pitch;$('custom-pitch').disabled=!engine.pitch;
 if(!engine.pitch&&s.condition==='pitch'){$('condition').value='preset';s.condition='preset';}
 const nativePitch=false;if($('custom-pitch').dataset.engine!==s.engine){Object.assign($('custom-pitch'),{min:nativePitch?'20':'-4',max:nativePitch?'80':'4',step:nativePitch?'1':'.25',value:nativePitch?'50':'0'});$('custom-pitch').dataset.engine=s.engine;s.custom.pitch=Number($('custom-pitch').value);}
 const p=controlsFor(s);
 document.querySelectorAll('.quadrant').forEach(el=>el.classList.toggle('chosen',el.dataset.emotion===s.emotion));
 $('target-name').textContent=QUADRANTS[s.emotion].name;
 $('rate-readout').textContent=p.words_per_minute?`${p.words_per_minute} words/min`:`${p.rate.toFixed(2)}× speed`;
 $('gain-readout').textContent=`${p.gain.toFixed(2)}× calibrated level`;$('pitch-readout').textContent=p.pitch===null?`${p.pitch_semitones>0?'+':''}${p.pitch_semitones.toFixed(2)} semitones · DSP`:`${p.pitch} / 100 · native`;
 $('voice-readout').textContent=p.voice;$('mechanism-name').textContent=engine.mechanism;$('engine-detail').textContent=engine.detail;
 $('custom-controls').hidden=s.condition!=='custom';$('custom-rate-value').textContent=`${s.custom.rate.toFixed(2)}×`;$('custom-gain-value').textContent=s.custom.gain.toFixed(2);$('custom-pitch-value').textContent=engine.pitch?s.custom.pitch:'Unavailable';
 $('char-count').textContent=`${$('message').value.length} / 800`;
 $('chat-engine').disabled=busy||Boolean(chat);$('nickname').disabled=busy||Boolean(mode==='explore'&&chat);
 $('chat-engine-label').textContent=chat?`${ENGINES[chat.engine].name} · ${chat.nickname}`:'Choose a voice for this conversation';
 const count=chat?.turns.length||0;$('chat-count').textContent=`${count} / ${MAX_EXCHANGES}`;$('chat-send').disabled=busy||count>=MAX_EXCHANGES;$('chat-message').disabled=busy||count>=MAX_EXCHANGES;
 $('engine-lock-note').textContent=chat?'Voice locked for this conversation. Start a new conversation to change it.':'The voice is fixed after your first message. Start a new conversation to change it.';
 if(count>=MAX_EXCHANGES&&!busy)$('chat-status').textContent='10 exchanges complete. Start a new conversation to continue.';
}
function setMode(next,{url=true}={}){
 if(busy)return;mode=next;
 $('studio').classList.toggle('blind',mode==='listening');$('studio').classList.toggle('exploring',mode==='explore');
 for(const [id,active] of [['mode-listening',mode==='listening'],['mode-test',mode==='line'],['mode-explore',mode==='explore']]){$(id).classList.toggle('active',active);$(id).setAttribute('aria-pressed',String(active));}
 $('workspace-title').textContent=mode==='listening'?'Listening test':mode==='line'?'Test Mode':'Explore Mode';$('listening-panel').hidden=mode!=='listening';$('interactive-panel').hidden=mode==='listening';$('line-panel').hidden=mode!=='line';$('explore-panel').hidden=mode!=='explore';
 // Every activity stays on its own page: the studio offers no link or switch to another activity.
 const listeningLink=document.querySelector('.topbar nav a[href="/?mode=listening"]');document.querySelector('.main-modes').hidden=true;if(listeningLink)listeningLink.hidden=true;
 if(mode==='listening')void ensureListening();
 // Opening Explore starts a hosted conversation model that sleeps between study sessions.
 if(mode==='explore')void checkDialogue();
 document.querySelectorAll('audio').forEach(a=>a.pause());
 if(mode!=='listening'){try{localStorage.setItem('echo-studio-exposed','1');}catch{}}
 if(mode==='explore'&&chat)$('nickname').value=chat.nickname;
 if(url){const u=new URL('/studio',location.origin);u.searchParams.set('mode',mode);history.pushState(null,'',u);}
 update();
}
function status(text){phase=text;$(mode==='explore'?'chat-status':'status').textContent=text;}
function lock(value){busy=value;document.querySelectorAll('#studio input,#studio select,#studio textarea,#studio button').forEach(el=>{if(!el.closest('#listening-content')&&!['cancel','chat-cancel'].includes(el.id))el.disabled=value;});$('cancel').hidden=!value||mode==='explore';$('chat-cancel').hidden=!value||mode!=='explore';if(!value){clearInterval(ticker);update();refreshMessageRatings();document.querySelectorAll('[data-compare-engine]').forEach(b=>{b.disabled=b.dataset.unsupported==='true';});}}
function eventFor(id){return event=>{if(id===job&&event.type==='progress')status(event.text);};}
function identity(){if(!$('identity-form').reportValidity())throw new Error('Enter your nickname and agree to storage before continuing.');return validateNickname($('nickname').value);}
// Another browser's nickname is refused before a new session starts; the server refuses it again when the session is saved.
const confirmedNicknames=new Set();
function nicknameError(message){$('nickname-error').textContent=message;$('nickname-error').hidden=!message;$('nickname').setCustomValidity(message);if(message)$('nickname').reportValidity();}
async function claimNickname(nickname){if(!confirmedNicknames.has(nickname)){if(!await nicknameAvailable(nickname,listenerId())){nicknameError(NICKNAME_TAKEN);return false;}confirmedNicknames.add(nickname);}nicknameError('');rememberNickname(nickname);return true;}
function syncFor(session){if(!syncs.has(session.session_id))syncs.set(session.session_id,new InteractiveSync(session,{onStatus:updateSaveStatus}));return syncs.get(session.session_id);}
function updateSaveStatus(){const pending=[...syncs.values()].filter(s=>interactivePending(s.session));$('interactive-save-status').dataset.state=pending.length?'offline':'saved';$('interactive-save-status').textContent=pending.length?'Messages, recordings or ratings are waiting to be saved. Keep this page open or retry saving.':'Messages, recordings and submitted ratings saved.';$('retry-interactive-save').hidden=!pending.length;refreshMessageRatings();}
function turnMetadata(session,record,input){return {order:session.turns.length+1,engine:record.engine,emotion:record.emotion,input_text:input,output_text:record.text,controls:Object.fromEntries(['engine','emotion','condition','rate','gain','pitch','voice','intensity','control_version','words_per_minute','length_scale','pitch_semitones','pitch_mechanism','level_reference','conditioning'].map(k=>[k,record[k]])),audio_metrics:Object.fromEntries(['processing_version','pitch_processing','pitch_shift_semitones','active_rms_dbfs','headroom_attenuation_db','peak','clipped_samples'].map(k=>[k,record[k]])),generation_metadata:{version:GENERATION_METADATA_VERSION,timing_scope:'tts_request_to_processed_wav_including_connect_queue_download',engine_source:record.engine==='kokoro'?'browser_kokoro':'python_service',service:record.service_metadata||null,dialogue:record.dialogue||null,timing:record.timing||null,exchange:record.exchange||null,client:record.client||null},audio_sha256:record.sha256,duration_s:record.duration_s,elapsed_s:record.elapsed_s,created_utc:record.created_utc};}
async function speech(text,s,id,session){const params=controlsFor(s),start=performance.now(),attempt_id=crypto.randomUUID(),hidden=visibilityWatch(),first=!requestedEngines.has(s.engine);requestedEngines.add(s.engine);let outcome='error',order=null;
 try{const result=await (s.engine==='kokoro'?neural:remote).run({task:'speech',text,params},eventFor(id));if(id!==job){outcome='cancelled';return null;}const sha256=await hashAudio(result.buffer);if(id!==job){outcome='cancelled';return null;}outcome='success';order=session.turns.length+1;const elapsed=performance.now()-start;
  // Where this voice's time went, plus the coarse device and network class that shape it (echo-generation-v2).
  return {...params,...result,text,sha256,elapsed_s:elapsed/1000,created_utc:new Date().toISOString(),purpose:'interactive_exploration_not_scored_study',timing:{...result.timing,total_s:seconds(elapsed),first_request_for_engine_in_page:first,page_hidden:hidden.stop()},client:deviceContext()};}
 finally{hidden.stop();if(id!==job)outcome='cancelled';void syncFor(session).attempt({attempt_id,engine:s.engine,emotion:s.emotion,status:outcome,stage:'tts',elapsed_s:(performance.now()-start)/1000,created_utc:new Date().toISOString(),turn_order:order});}
}

function addRecord(record,session,order){
 lastComparedEngine=record.engine;$('baseline').textContent=`Neutral controls · ${ENGINES[record.engine].name}`;
 document.querySelectorAll('[data-compare-engine]').forEach(b=>{b.dataset.unsupported=String(lastLine?.selection.condition==='pitch'&&!ENGINES[b.dataset.compareEngine].pitch);});
 if(!records.length)$('results').replaceChildren();records.push(record);const el=document.createElement('article');el.className='turn';
 const top=document.createElement('div');top.className='turn-top';const title=document.createElement('h3');title.textContent=ENGINES[record.engine].name;const badge=document.createElement('span');badge.className='turn-badge';badge.textContent=`TARGET ${QUADRANTS[record.emotion].name.toUpperCase()} · ${record.condition.toUpperCase()}`;top.append(title,badge);
 const text=document.createElement('blockquote');text.textContent=record.text;
 const audio=document.createElement('audio');audio.controls=true;audio.preload='metadata';audio.setAttribute('aria-label',`${title.textContent}, ${record.condition}, ${QUADRANTS[record.emotion].name}`);record.url=URL.createObjectURL(new Blob([record.buffer],{type:'audio/wav'}));audio.src=record.url;
 const meta=document.createElement('div');meta.className='turn-meta';meta.textContent=`${record.duration_s.toFixed(2)}s audio · ${record.elapsed_s.toFixed(1)}s generation · speed ${record.rate.toFixed(2)}× · gain ${record.gain.toFixed(2)}${record.pitch!==null?` · native pitch ${record.pitch}`:` · pitch ${record.pitch_semitones>0?'+':''}${record.pitch_semitones.toFixed(2)} st (DSP)`}`;
 const link=document.createElement('a');link.href=audio.src;link.download=`echo-${record.engine}-${record.emotion}-${record.condition}-${records.length}.wav`;link.textContent='Download WAV';trackPlayback(audio,()=>({item_order:order}),event=>syncFor(session).playback(event));el.append(top,text,audio,meta,link,messageRatingForm(audio,session,order,syncFor(session)));$('results').prepend(el);
 if(records.length>12){const old=records.shift();URL.revokeObjectURL(old.url);$('results').lastElementChild.remove();}
}
async function runLine({reuse=false,engine,condition}={}){
 if(busy)return;let nickname;try{nickname=identity();}catch(e){$('error').textContent=e.message;$('error').hidden=false;return;}
 const id=++job;let s=selection();if(engine)s.engine=engine;if(condition)s.condition=condition;
 $('error').hidden=true;started=Date.now();lock(true);status('Preparing your voice…');ticker=setInterval(()=>{$('status').textContent=`${phase} · ${Math.floor((Date.now()-started)/1000)}s`;},1000);
 try{
  if(!await claimNickname(nickname)){status('Change the nickname to continue.');return;}
  let text;if(reuse){if(!lastLine)throw new Error('Generate a line first.');text=lastLine.text;s={...lastLine.selection,engine:engine||lastLine.selection.engine,condition:condition||lastLine.selection.condition};}else{text=validateText($('message').value);lastLine={text,selection:{...s}};}
  if(!lineSession||lineSession.nickname!==nickname||lineSession.turns.length>=12||(lineSession.attempts?.length||0)>=100)lineSession=createInteractiveSession('line',nickname,null);
  const record=await speech(text,s,id,lineSession);if(!record)return;
  const turn=turnMetadata(lineSession,record,text);void syncFor(lineSession).add(turn,record.buffer);addRecord({...record,nickname},lineSession,turn.order);$('compare-actions').hidden=false;status('Voice ready. Listen and compare the expression.');
 }catch(e){if(id!==job)return;$('error').textContent=e.message||String(e);$('error').hidden=false;status('Operation stopped. Adjust the settings and retry.');}finally{if(id===job)lock(false);}
}
function bubble(role,text){const el=document.createElement('article');el.className='chat-bubble '+role;if(text){const p=document.createElement('p');p.textContent=text;el.append(p);}return el;}
async function runChat(){
 if(busy||(chat?.turns.length||0)>=MAX_EXCHANGES)return;let nickname,input;try{nickname=identity();input=validateText($('chat-message').value);}catch(e){$('chat-error').textContent=e.message;$('chat-error').hidden=false;return;}
 if(!chat){lock(true);const free=await claimNickname(nickname);lock(false);if(!free){status('Change the nickname to continue.');return;}chat=createInteractiveSession('explore',nickname,$('chat-engine').value);chat.audioUrls=[];}
 const s=selection(),id=++job;started=Date.now();$('chat-error').hidden=true;lock(true);status('Preparing your voice reply…');
 if(!$('chat-messages').querySelector('.chat-bubble'))$('chat-messages').replaceChildren();
 const userBubble=bubble('user',input),pending=bubble('assistant','Preparing a voice message…');$('chat-messages').append(userBubble,pending);$('chat-messages').scrollTop=$('chat-messages').scrollHeight;
 ticker=setInterval(()=>{$('chat-status').textContent=`${phase} · ${Math.floor((Date.now()-started)/1000)}s`;},1000);
 // The exchange is timed from here, with the message on screen, until its voice reply is ready.
 const exchangeStart=performance.now(),exchangeHidden=visibilityWatch();
 try{
  const previous=chat.turns.flatMap(t=>[{role:'user',content:t.input_text},{role:'assistant',content:t.output_text}]);
  status('Writing a reply with your chosen emotion…');replyRequest=new AbortController();
  // The server's metrics line for this reply names the conversation, planned message and attempt, so its model time joins the saved message.
  const session=chat,replyAttempt=crypto.randomUUID(),replyStart=performance.now();let generated,retries=0,replyOutcome='error';
  try{generated=await requestReplyWhenReady({text:input,emotion:s.emotion,history:previous,link:{session_id:session.session_id,turn_order:session.turns.length+1,attempt_id:replyAttempt}},{signal:replyRequest.signal,onWaiting:()=>{retries++;status('The conversation model is starting after a quiet period. This can take about two minutes…');}});replyOutcome='success';}
  finally{replyRequest=null;const cancelled=id!==job;
   // A successful reply's diagnostic travels with the message save; a failed or cancelled reply is sent at once.
   void syncFor(session).attempt({attempt_id:replyAttempt,engine:s.engine,emotion:s.emotion,status:cancelled?'cancelled':replyOutcome,stage:'dialogue',elapsed_s:(performance.now()-replyStart)/1000,created_utc:new Date().toISOString(),turn_order:null},{sync:cancelled||replyOutcome!=='success'});}
  if(id!==job)return;const replyWait=performance.now()-replyStart;
  status(`Voicing the reply with ${ENGINES[s.engine].name}…`);const record=await speech(validateText(generated.text),s,id,session);if(!record)return;
  record.dialogue={prompt_version:generated.prompt_version??null,gate:generated.gate??null,attempt_id:replyAttempt,reply_wait_s:seconds(replyWait),model_start_retries:retries,check:generated.check??null};
  record.exchange={end_to_end_s:seconds(performance.now()-exchangeStart),page_hidden:exchangeHidden.stop()};
  pending.replaceChildren();const label=document.createElement('span');label.className='voice-label';label.textContent=`Voice message · ${record.duration_s.toFixed(1)}s`;
  const audio=document.createElement('audio');audio.controls=true;audio.preload='metadata';audio.setAttribute('aria-label','ECHO voice reply');const url=URL.createObjectURL(new Blob([record.buffer],{type:'audio/wav'}));chat.audioUrls.push(url);audio.src=url;
  const button=document.createElement('button');button.type='button';button.className='transcript-button';button.textContent='Show transcript';button.setAttribute('aria-expanded','false');
  const transcript=document.createElement('p');transcript.className='transcript';transcript.textContent=record.text;transcript.hidden=true;transcript.id='transcript-'+crypto.randomUUID();button.setAttribute('aria-controls',transcript.id);button.addEventListener('click',()=>{transcript.hidden=!transcript.hidden;button.textContent=transcript.hidden?'Show transcript':'Hide transcript';button.setAttribute('aria-expanded',String(!transcript.hidden));});
  const meta=document.createElement('small');meta.textContent=`${ENGINES[record.engine].name} · ${QUADRANTS[record.emotion].name}`;pending.append(label,audio,button,transcript,meta);
  const turn=turnMetadata(chat,record,input);void syncFor(chat).add(turn,record.buffer);pending.append(messageRatingForm(audio,chat,turn.order,syncFor(chat)));$('chat-message').value='';status('Voice reply ready. Play it or open the transcript.');$('chat-messages').scrollTop=$('chat-messages').scrollHeight;
  // Browsers may require another click after model loading; the play control always remains available.
  const conversation=chat,saveEvent=event=>syncFor(conversation).playback(event);trackPlayback(audio,()=>({item_order:turn.order}),saveEvent);trackTranscript(button,transcript,audio,()=>({item_order:turn.order}),saveEvent);
  document.querySelectorAll('audio').forEach(a=>{if(a!==audio)a.pause();});audio.dataset.autoplay='1';void audio.play().catch(()=>{delete audio.dataset.autoplay;});
 }catch(e){if(id!==job)return;userBubble.remove();pending.remove();$('chat-error').textContent=e.message||String(e);$('chat-error').hidden=false;status('No exchange was counted. Your message is kept so you can retry.');}
 finally{exchangeHidden.stop();if(id!==job){userBubble.remove();pending.remove();}else lock(false);}
}
function cancel(){job++;replyRequest?.abort();replyRequest=null;remote.reset();neural.reset();lock(false);status('Cancelled. Your message is kept; you can retry.');}
$('voice-form').addEventListener('submit',e=>{e.preventDefault();void runLine();});$('chat-form').addEventListener('submit',e=>{e.preventDefault();void runChat();});$('identity-form').addEventListener('submit',e=>e.preventDefault());
$('cancel').addEventListener('click',cancel);$('chat-cancel').addEventListener('click',cancel);
$('mode-listening').addEventListener('click',()=>setMode('listening'));$('mode-test').addEventListener('click',()=>setMode('line'));$('mode-explore').addEventListener('click',()=>setMode('explore'));
window.addEventListener('popstate',()=>setMode(new URLSearchParams(location.search).get('mode')||'line',{url:false}));
$('new-conversation').addEventListener('click',()=>{if(busy)return;chat?.audioUrls?.forEach(url=>URL.revokeObjectURL(url));chat=null;$('chat-messages').replaceChildren();$('chat-error').hidden=true;$('chat-message').value='';$('chat-status').textContent='New conversation. Choose one TTS engine, then send your first message.';update();});
$('nickname').value=readNickname();$('nickname').addEventListener('change',()=>{let name;try{name=validateNickname($('nickname').value);}catch(e){$('nickname').setCustomValidity(e.message);return;}void claimNickname(name);});$('nickname').addEventListener('input',()=>nicknameError(''));
for(const id of ['engine','condition','custom-rate','custom-gain','custom-pitch','message','chat-engine'])$(id).addEventListener('input',update);document.querySelectorAll('input[name=emotion]').forEach(el=>el.addEventListener('change',update));
document.querySelectorAll('[data-compare-engine]').forEach(button=>button.addEventListener('click',()=>void runLine({reuse:true,engine:button.dataset.compareEngine})));
$('baseline').addEventListener('click',()=>void runLine({reuse:true,engine:lastComparedEngine,condition:'neutral'}));
$('export').addEventListener('click',()=>{const turns=records.map(({buffer,url,envelope,...rest})=>rest),url=URL.createObjectURL(new Blob([JSON.stringify({project:'ECHO',purpose:'interactive_exploration_not_scored_study',turns},null,2)],{type:'application/json'})),a=document.createElement('a');a.href=url;a.download='echo-voice-session.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);});
$('retry-interactive-save').addEventListener('click',()=>syncs.forEach(s=>{if(interactivePending(s.session))void s.sync();}));window.addEventListener('online',()=>syncs.forEach(s=>{if(interactivePending(s.session))void s.sync();}));
// Playback events travel with the next save; this sends the ones recorded after a session's last save.
setInterval(()=>syncs.forEach(s=>{if(!interactivePending(s.session))void s.flushPlayback();}),60000);

for(const session of loadOutbox())if(session?.turns?.length)void syncFor(session).sync();
const initial=new URLSearchParams(location.search).get('mode');setMode(['listening','line','explore'].includes(initial)?initial:'line',{url:false});


async function ensureListening(){
 if(listeningLoaded||listeningLoading)return;listeningLoading=true;
 try{const response=await fetch('/listen.html');if(!response.ok)throw new Error('The listening test could not load.');const html=await response.text(),doc=new DOMParser().parseFromString(html,'text/html'),source=doc.querySelector('.study-main');if(!source)throw new Error('Listening test content is missing.');const content=document.createElement('div');content.className='study-main embedded-study';content.append(...source.childNodes);$('listening-content').replaceChildren(content);await import('./listen.js');listeningLoaded=true;}catch(error){$('listening-content').replaceChildren();const p=document.createElement('p');p.textContent=error.message;const button=document.createElement('button');button.className='secondary';button.textContent='Retry loading';button.addEventListener('click',()=>void ensureListening());$('listening-content').append(p,button);}finally{listeningLoading=false;}
}
