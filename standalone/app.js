import {TEST_ENGINES,EXPLORE_ENGINES} from './engine-catalog.js';
import {messageRatingForm,refreshMessageRatings} from './message-rating-ui.js';
import {interactivePending} from './message-rating.js';
import {RemoteSpeechClient} from './remote-speech.js';
import {EMOTIONS,ENGINES,controlsFor,validateText} from './voice-controls.js';
import {requestReplyWhenReady,checkDialogue} from './dialogue-client.js';
import {NeuralClient} from './neural-client.js';
import {hashAudio} from './audio-utils.js';
import {readNickname,rememberNickname,MAX_EXCHANGES} from './participant.js';
import {createInteractiveSession,InteractiveSync,loadOutbox} from './interactive-sync.js';
import {trackPlayback,trackTranscript} from './playback-log.js';
const $=id=>document.getElementById(id),neural=new NeuralClient();
const remote=new RemoteSpeechClient();
let listeningLoaded=false,listeningLoading=false;
let mode='listening',busy=false,job=0,ticker,started,phase='',records=[],lastLine=null,lastComparedEngine=null,chat=null,lineSession=null,replyRequest=null;
const syncs=new Map();
function selection(){return {emotion:document.querySelector('input[name=emotion]:checked').value,intensity:1,engine:mode==='explore'?(chat?.engine||$('chat-engine').value):$('engine').value,condition:mode==='explore'?'preset':$('condition').value,custom:{rate:Number($('custom-rate').value)/100,gain:Number($('custom-gain').value)/100,pitch:Number($('custom-pitch').value)}};}
for(const [id,engines] of [['engine',TEST_ENGINES],['chat-engine',EXPLORE_ENGINES]])$(id).replaceChildren(...engines.map(e=>new Option(ENGINES[e].name,e)));
$('compare-actions').querySelectorAll('[data-compare-engine]').forEach(b=>b.remove());
for(const e of TEST_ENGINES){const button=document.createElement('button');button.type='button';button.className='secondary';button.dataset.compareEngine=e;button.textContent='Compare '+ENGINES[e].name;$('compare-actions').append(button);}
function update(){
 const s=selection(),e=EMOTIONS[s.emotion],engine=ENGINES[s.engine];
 for(const option of $('condition').options)option.disabled=s.engine!=='kokoro'&&!['preset','neutral'].includes(option.value);
 if($('condition').selectedOptions[0].disabled){$('condition').value='preset';s.condition='preset';}
 $('pitch-option').disabled=!engine.pitch;$('custom-pitch').disabled=!engine.pitch;
 if(!engine.pitch&&s.condition==='pitch'){$('condition').value='preset';s.condition='preset';}
 const nativePitch=false;if($('custom-pitch').dataset.engine!==s.engine){Object.assign($('custom-pitch'),{min:nativePitch?'20':'-4',max:nativePitch?'80':'4',step:nativePitch?'1':'.25',value:nativePitch?'50':'0'});$('custom-pitch').dataset.engine=s.engine;s.custom.pitch=Number($('custom-pitch').value);}
 const p=controlsFor(s);
 document.querySelectorAll('.emotion').forEach(el=>el.classList.toggle('chosen',el.dataset.emotion===s.emotion));
 $('target-name').textContent=e.name;$('target-coordinates').textContent=`Valence ${e.v>0?'+':''}${e.v.toFixed(2)} · Arousal ${e.a>0?'+':''}${e.a.toFixed(2)}`;
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
 // Test mode and Explore stay on their own activity: their pages offer no way to switch to another activity.
 const inActivity=mode!=='listening',listeningLink=document.querySelector('.topbar nav a[href="/?mode=listening"]');document.querySelector('.main-modes').hidden=inActivity;if(listeningLink)listeningLink.hidden=inActivity;
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
function identity(){if(!$('identity-form').reportValidity())throw new Error('Enter your nickname and agree to storage before continuing.');return rememberNickname($('nickname').value);}
function syncFor(session){if(!syncs.has(session.session_id))syncs.set(session.session_id,new InteractiveSync(session,{onStatus:updateSaveStatus}));return syncs.get(session.session_id);}
function updateSaveStatus(){const pending=[...syncs.values()].filter(s=>interactivePending(s.session));$('interactive-save-status').dataset.state=pending.length?'offline':'saved';$('interactive-save-status').textContent=pending.length?'Messages, recordings or ratings are waiting to be saved. Keep this page open or retry saving.':'Messages, recordings and submitted ratings saved.';$('retry-interactive-save').hidden=!pending.length;refreshMessageRatings();}
function turnMetadata(session,record,input){return {order:session.turns.length+1,engine:record.engine,emotion:record.emotion,input_text:input,output_text:record.text,controls:Object.fromEntries(['engine','emotion','condition','rate','gain','pitch','voice','intensity','control_version','words_per_minute','length_scale','pitch_semitones','pitch_mechanism','level_reference','conditioning'].map(k=>[k,record[k]])),audio_metrics:Object.fromEntries(['processing_version','pitch_processing','pitch_shift_semitones','active_rms_dbfs','headroom_attenuation_db','peak','clipped_samples'].map(k=>[k,record[k]])),generation_metadata:{version:'echo-generation-v1',timing_scope:'tts_request_to_processed_wav_including_connect_queue_download',engine_source:record.engine==='kokoro'?'browser_kokoro':'python_service',service:record.service_metadata||null,dialogue:record.dialogue||null},audio_sha256:record.sha256,duration_s:record.duration_s,elapsed_s:record.elapsed_s,created_utc:record.created_utc};}
async function speech(text,s,id,session){const params=controlsFor(s),start=performance.now(),attempt_id=crypto.randomUUID();let outcome='error',order=null;
 try{const result=await (s.engine==='kokoro'?neural:remote).run({task:'speech',text,params},eventFor(id));if(id!==job){outcome='cancelled';return null;}const sha256=await hashAudio(result.buffer);if(id!==job){outcome='cancelled';return null;}outcome='success';order=session.turns.length+1;return {...params,...result,text,sha256,elapsed_s:(performance.now()-start)/1000,created_utc:new Date().toISOString(),purpose:'interactive_exploration_not_scored_study'};}
 finally{if(id!==job)outcome='cancelled';void syncFor(session).attempt({attempt_id,engine:s.engine,emotion:s.emotion,status:outcome,stage:'tts',elapsed_s:(performance.now()-start)/1000,created_utc:new Date().toISOString(),turn_order:order});}
}

function addRecord(record,session,order){
 lastComparedEngine=record.engine;$('baseline').textContent=`Neutral controls · ${ENGINES[record.engine].name}`;
 document.querySelectorAll('[data-compare-engine]').forEach(b=>{b.dataset.unsupported=String(lastLine?.selection.condition==='pitch'&&!ENGINES[b.dataset.compareEngine].pitch);});
 if(!records.length)$('results').replaceChildren();records.push(record);const el=document.createElement('article');el.className='turn';
 const top=document.createElement('div');top.className='turn-top';const title=document.createElement('h3');title.textContent=ENGINES[record.engine].name;const badge=document.createElement('span');badge.className='turn-badge';badge.textContent=`TARGET ${EMOTIONS[record.emotion].name.toUpperCase()} · ${record.condition.toUpperCase()}`;top.append(title,badge);
 const text=document.createElement('blockquote');text.textContent=record.text;
 const audio=document.createElement('audio');audio.controls=true;audio.preload='metadata';audio.setAttribute('aria-label',`${title.textContent}, ${record.condition}, ${EMOTIONS[record.emotion].name}`);record.url=URL.createObjectURL(new Blob([record.buffer],{type:'audio/wav'}));audio.src=record.url;
 const meta=document.createElement('div');meta.className='turn-meta';meta.textContent=`${record.duration_s.toFixed(2)}s audio · ${record.elapsed_s.toFixed(1)}s generation · speed ${record.rate.toFixed(2)}× · gain ${record.gain.toFixed(2)}${record.pitch!==null?` · native pitch ${record.pitch}`:` · pitch ${record.pitch_semitones>0?'+':''}${record.pitch_semitones.toFixed(2)} st (DSP)`}`;
 const link=document.createElement('a');link.href=audio.src;link.download=`echo-${record.engine}-${record.emotion}-${record.condition}-${records.length}.wav`;link.textContent='Download WAV';trackPlayback(audio,()=>({item_order:order}),event=>syncFor(session).playback(event));el.append(top,text,audio,meta,link,messageRatingForm(audio,session,order,syncFor(session)));$('results').append(el);$('export').hidden=false;
 if(records.length>12){const old=records.shift();URL.revokeObjectURL(old.url);$('results').firstElementChild.remove();}
}
async function runLine({reuse=false,engine,condition}={}){
 if(busy)return;let nickname;try{nickname=identity();}catch(e){$('error').textContent=e.message;$('error').hidden=false;return;}
 const id=++job;let s=selection();if(engine)s.engine=engine;if(condition)s.condition=condition;
 $('error').hidden=true;started=Date.now();lock(true);status('Preparing your voice…');ticker=setInterval(()=>{$('status').textContent=`${phase} · ${Math.floor((Date.now()-started)/1000)}s`;},1000);
 try{
  let text;if(reuse){if(!lastLine)throw new Error('Generate a line first.');text=lastLine.text;s={...lastLine.selection,engine:engine||lastLine.selection.engine,condition:condition||lastLine.selection.condition};}else{text=validateText($('message').value);lastLine={text,selection:{...s}};}
  if(!lineSession||lineSession.nickname!==nickname||lineSession.turns.length>=12||(lineSession.attempts?.length||0)>=100)lineSession=createInteractiveSession('line',nickname,null);
  const record=await speech(text,s,id,lineSession);if(!record)return;
  const turn=turnMetadata(lineSession,record,text);void syncFor(lineSession).add(turn,record.buffer);addRecord({...record,nickname},lineSession,turn.order);$('compare-actions').hidden=false;status('Voice ready. Listen and compare the expression.');
 }catch(e){if(id!==job)return;$('error').textContent=e.message||String(e);$('error').hidden=false;status('Operation stopped. Adjust the settings and retry.');}finally{if(id===job)lock(false);}
}
function bubble(role,text){const el=document.createElement('article');el.className='chat-bubble '+role;if(text){const p=document.createElement('p');p.textContent=text;el.append(p);}return el;}
async function runChat(){
 if(busy||(chat?.turns.length||0)>=MAX_EXCHANGES)return;let nickname,input;try{nickname=identity();input=validateText($('chat-message').value);}catch(e){$('chat-error').textContent=e.message;$('chat-error').hidden=false;return;}
 if(!chat){chat=createInteractiveSession('explore',nickname,$('chat-engine').value);chat.audioUrls=[];}
 const s=selection(),id=++job;started=Date.now();$('chat-error').hidden=true;lock(true);status('Preparing your voice reply…');
 if(!$('chat-messages').querySelector('.chat-bubble'))$('chat-messages').replaceChildren();
 const userBubble=bubble('user',input),pending=bubble('assistant','Preparing a voice message…');$('chat-messages').append(userBubble,pending);$('chat-messages').scrollTop=$('chat-messages').scrollHeight;
 ticker=setInterval(()=>{$('chat-status').textContent=`${phase} · ${Math.floor((Date.now()-started)/1000)}s`;},1000);
 try{
  const previous=chat.turns.flatMap(t=>[{role:'user',content:t.input_text},{role:'assistant',content:t.output_text}]);
  status('Writing a reply with your chosen emotion…');replyRequest=new AbortController();
  const generated=await requestReplyWhenReady({text:input,emotion:s.emotion,history:previous},{signal:replyRequest.signal,onWaiting:()=>status('The conversation model is starting after a quiet period. This can take about two minutes…')});replyRequest=null;if(id!==job)return;
  status(`Voicing the reply with ${ENGINES[s.engine].name}…`);const record=await speech(validateText(generated.text),s,id,chat);if(!record)return;record.dialogue={prompt_version:generated.prompt_version??null,gate:generated.gate??null};
  pending.replaceChildren();const label=document.createElement('span');label.className='voice-label';label.textContent=`Voice message · ${record.duration_s.toFixed(1)}s`;
  const audio=document.createElement('audio');audio.controls=true;audio.preload='metadata';audio.setAttribute('aria-label','ECHO voice reply');const url=URL.createObjectURL(new Blob([record.buffer],{type:'audio/wav'}));chat.audioUrls.push(url);audio.src=url;
  const button=document.createElement('button');button.type='button';button.className='transcript-button';button.textContent='Show transcript';button.setAttribute('aria-expanded','false');
  const transcript=document.createElement('p');transcript.className='transcript';transcript.textContent=record.text;transcript.hidden=true;transcript.id='transcript-'+crypto.randomUUID();button.setAttribute('aria-controls',transcript.id);button.addEventListener('click',()=>{transcript.hidden=!transcript.hidden;button.textContent=transcript.hidden?'Show transcript':'Hide transcript';button.setAttribute('aria-expanded',String(!transcript.hidden));});
  const meta=document.createElement('small');meta.textContent=`${ENGINES[record.engine].name} · ${EMOTIONS[record.emotion].name}`;pending.append(label,audio,button,transcript,meta);
  const turn=turnMetadata(chat,record,input);void syncFor(chat).add(turn,record.buffer);pending.append(messageRatingForm(audio,chat,turn.order,syncFor(chat)));$('chat-message').value='';status('Voice reply ready. Play it or open the transcript.');$('chat-messages').scrollTop=$('chat-messages').scrollHeight;
  // Browsers may require another click after model loading; the play control always remains available.
  const conversation=chat,saveEvent=event=>syncFor(conversation).playback(event);trackPlayback(audio,()=>({item_order:turn.order}),saveEvent);trackTranscript(button,transcript,audio,()=>({item_order:turn.order}),saveEvent);
  document.querySelectorAll('audio').forEach(a=>{if(a!==audio)a.pause();});audio.dataset.autoplay='1';void audio.play().catch(()=>{delete audio.dataset.autoplay;});
 }catch(e){if(id!==job)return;userBubble.remove();pending.remove();$('chat-error').textContent=e.message||String(e);$('chat-error').hidden=false;status('No exchange was counted. Your message is kept so you can retry.');}
 finally{if(id!==job){userBubble.remove();pending.remove();}else lock(false);}
}
function cancel(){job++;replyRequest?.abort();replyRequest=null;remote.reset();neural.reset();lock(false);status('Cancelled. Your message is kept; you can retry.');}
$('voice-form').addEventListener('submit',e=>{e.preventDefault();void runLine();});$('chat-form').addEventListener('submit',e=>{e.preventDefault();void runChat();});$('identity-form').addEventListener('submit',e=>e.preventDefault());
$('cancel').addEventListener('click',cancel);$('chat-cancel').addEventListener('click',cancel);
$('mode-listening').addEventListener('click',()=>setMode('listening'));$('mode-test').addEventListener('click',()=>setMode('line'));$('mode-explore').addEventListener('click',()=>setMode('explore'));
window.addEventListener('popstate',()=>setMode(new URLSearchParams(location.search).get('mode')||'line',{url:false}));
$('new-conversation').addEventListener('click',()=>{if(busy)return;chat?.audioUrls?.forEach(url=>URL.revokeObjectURL(url));chat=null;$('chat-messages').replaceChildren();$('chat-error').hidden=true;$('chat-message').value='';$('chat-status').textContent='New conversation. Choose one TTS engine, then send your first message.';update();});
$('nickname').value=readNickname();$('nickname').addEventListener('change',()=>{try{rememberNickname($('nickname').value);$('nickname').setCustomValidity('');}catch(e){$('nickname').setCustomValidity(e.message);}});$('nickname').addEventListener('input',()=>$('nickname').setCustomValidity(''));
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
