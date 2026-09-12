// Records every play, pause, finish and seek of an audio element with its playback position, for the listening-behaviour log.
export const PLAYBACK_EVENTS=['play','pause','ended','seeked'];
const round=(value,digits)=>Number.isFinite(value)?Number(value.toFixed(digits)):null;
// context() names the clip or message the element is playing when the event fires; record() receives one event.
export function trackPlayback(audio,context,record){
 for(const type of PLAYBACK_EVENTS)audio.addEventListener(type,()=>{
  const where=context();if(!where)return;
  const autoplay=type==='play'&&audio.dataset?.autoplay==='1';if(autoplay)delete audio.dataset.autoplay;
  record({event_id:crypto.randomUUID(),event:type,item_order:where.item_order,item_id:where.item_id??null,position_s:round(audio.currentTime,3)??0,duration_s:round(audio.duration,3),playback_rate:round(audio.playbackRate,2)??1,autoplay,client_utc:new Date().toISOString()});
 });
}
