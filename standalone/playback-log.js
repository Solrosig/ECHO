// Records every play, pause, finish and seek of an audio element with its playback position, and each opening or closing
// of a message transcript, for the listening-behaviour log.
export const MEDIA_EVENTS=['play','pause','ended','seeked'];
export const TRANSCRIPT_EVENTS=['transcript_open','transcript_close'];
const round=(value,digits)=>Number.isFinite(value)?Number(value.toFixed(digits)):null;
const snapshot=(audio,type,where,autoplay=false)=>({event_id:crypto.randomUUID(),event:type,item_order:where.item_order,item_id:where.item_id??null,position_s:round(audio.currentTime,3)??0,duration_s:round(audio.duration,3),playback_rate:round(audio.playbackRate,2)??1,autoplay,client_utc:new Date().toISOString()});
// context() names the clip or message the element is playing when the event fires; record() receives one event.
export function trackPlayback(audio,context,record){
 for(const type of MEDIA_EVENTS)audio.addEventListener(type,()=>{
  const where=context();if(!where)return;
  const autoplay=type==='play'&&audio.dataset?.autoplay==='1';if(autoplay)delete audio.dataset.autoplay;
  record(snapshot(audio,type,where,autoplay));
 });
}
// Register after the button's own toggle, so the transcript's new visibility decides between open and close.
// The voice position shows whether the transcript was opened before the message finished playing.
export function trackTranscript(button,transcript,audio,context,record){
 button.addEventListener('click',()=>{const where=context();if(where)record(snapshot(audio,transcript.hidden?'transcript_close':'transcript_open',where));});
}
