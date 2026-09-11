import {savePendingAudio,loadPendingAudio,deletePendingAudio} from './audio-outbox.js';
import {newSessionToken} from './study-sync.js';
import {validateNickname,validateConversationTurn} from './participant.js';
import {validateMessageRating,interactivePending} from './message-rating.js';
export const INTERACTIVE_VERSION='echo-interactive-20260907-v3';
const OUTBOX='echo-interactive-outbox-v1';
export function createInteractiveSession(mode,nickname,engine){return {session_id:'X-'+crypto.randomUUID().replaceAll('-','').toUpperCase(),nickname:validateNickname(nickname),mode,engine,record_type:typeof location!=='undefined'&&new URLSearchParams(location.search).get('test')==='1'?'technical_test':'interactive_exploration',version:INTERACTIVE_VERSION,consent:true,consent_utc:new Date().toISOString(),token:newSessionToken(),turns:[],saved_count:0};}
export function loadOutbox(){try{const data=JSON.parse(localStorage.getItem(OUTBOX)||'[]');return Array.isArray(data)?data:[];}catch{return [];}}
function persist(session){
 const queued=loadOutbox().filter(s=>s.session_id!==session.session_id);
 if(interactivePending(session))queued.push(session);
 try{localStorage.setItem(OUTBOX,JSON.stringify(queued));return true;}catch{return false;}
}
export class InteractiveSync{
 constructor(session,{fetcher=fetch,onStatus=()=>{}}={}){Object.assign(this,{session,fetcher,onStatus});this.running=null;this.dirty=false;this.audio=new Map();}
 async request(path,data){const c=new AbortController(),timer=setTimeout(()=>c.abort(),15000);try{const response=await this.fetcher.call(globalThis,path,{method:'POST',headers:{'Content-Type':'application/json',Authorization:`Bearer ${this.session.token}`},body:JSON.stringify(data),signal:c.signal});const result=await response.json();if(!response.ok){const e=new Error(result.error||'The database could not save this session.');e.status=response.status;throw e;}return result;}finally{clearTimeout(timer);}}
 attempt(event){this.session.attempts||=[];this.session.attempts.push(event);persist(this.session);return this.sync();}
 add(turn,buffer){validateConversationTurn(this.session,turn);this.session.turns.push(turn);
  if(buffer){this.audio.set(turn.order,buffer);this.session.audio_orders||=[];this.session.audio_orders.push(turn.order);}
  persist(this.session);this.onStatus({state:'saving'});
  const stage=buffer?savePendingAudio(`${this.session.session_id}/${turn.order}`,buffer).catch(()=>{}):Promise.resolve();
  return stage.then(()=>this.sync());
 }
 async uploadAudio(order){
  const key=`${this.session.session_id}/${order}`,buffer=this.audio.get(order)||await loadPendingAudio(key);
  if(!buffer)throw new Error('The browser no longer has a queued recording. Keep the original page open or retain its WAV download.');
  const c=new AbortController(),timer=setTimeout(()=>c.abort(),60000);try{
   const r=await this.fetcher.call(globalThis,`/api/interactive/sessions/${this.session.session_id}/audio/${order}`,{method:'PUT',headers:{'Content-Type':'audio/wav',Authorization:`Bearer ${this.session.token}`},body:buffer,signal:c.signal});const result=await r.json();
   if(!r.ok){const error=new Error(result.error||'Audio archive unavailable.');error.status=r.status;throw error;}
   if(!result.archived||result.sha256!==this.session.turns.find(t=>t.order===order).audio_sha256)throw new Error('Audio archive acknowledgement does not match.');
   this.session.saved_audio_orders||=[];if(!this.session.saved_audio_orders.includes(order))this.session.saved_audio_orders.push(order);persist(this.session);this.audio.delete(order);await deletePendingAudio(key).catch(()=>{});
  }finally{clearTimeout(timer);}
 }
 rate(order,rating){validateMessageRating(rating);if(!this.session.turns.some(t=>t.order===order))throw new Error('Save the generated message before rating it.');this.session.ratings||={};if(this.session.ratings[order]&&JSON.stringify(this.session.ratings[order])!==JSON.stringify(rating))throw new Error('This message has already been rated.');this.session.ratings[order]=rating;persist(this.session);return this.sync();}
 sync(){this.dirty=true;if(this.running)return this.running;this.running=this.drain().finally(()=>{this.running=null;});return this.running;}
 async drain(){try{while(this.dirty){this.dirty=false;this.onStatus({state:'saving',saved:this.session.saved_count});const {token,turns,saved_count,audioUrls,ratings,saved_rating_count,saved_rating_orders,audio_orders,saved_audio_orders,attempts,saved_attempt_orders,...metadata}=this.session;await this.request('/api/interactive/sessions',metadata);const result=turns.length?await this.request(`/api/interactive/sessions/${this.session.session_id}/turns`,{turns}):{saved_count:0};this.session.saved_count=result.saved_count;
  if(this.session.attempts?.length){const ack=await this.request(`/api/interactive/sessions/${this.session.session_id}/attempts`,{attempts:this.session.attempts});this.session.saved_attempt_orders=ack.orders;}
  const pending=Object.entries(this.session.ratings||{}).map(([order,rating])=>({order:Number(order),rating}));
  if(pending.length){const rated=await this.request(`/api/interactive/sessions/${this.session.session_id}/ratings`,{ratings:pending});this.session.saved_rating_count=rated.saved_count;this.session.saved_rating_orders=rated.orders;}
  for(const order of this.session.audio_orders||[])if(!(this.session.saved_audio_orders||[]).includes(order))await this.uploadAudio(order);
  persist(this.session);this.onStatus({state:'saved',saved:result.saved_count});}}catch(error){this.dirty=true;const retained=persist(this.session);this.onStatus({state:[400,401,403,409,410].includes(error.status)?'conflict':'offline',saved:this.session.saved_count,message:retained?'Waiting for the database. Messages, ratings or recordings may still be queued. Keep this page open and retry saving.':'The browser backup is unavailable. Keep this page open and retry saving.'});}}
}
