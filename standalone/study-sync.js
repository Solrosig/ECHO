export const COLLECTION_VERSION='echo-collection-sqlite-20260907-v5';
export function newSessionToken() { return Array.from(crypto.getRandomValues(new Uint8Array(32)),n=>n.toString(16).padStart(2,'0')).join(''); }
export function wireRows(session,trials) {
  const rows=session.rows.map(r=>({order:r.order,item_id:r.item_id,block_id:r.block_id,valence:r.valence,arousal:r.arousal,naturalness:r.naturalness,target_match:r.target_match,play_count:r.play_count,completed_audio:r.completed_audio,elapsed_s:Number(r.elapsed_s),created_utc:r.created_utc}));
  if(session.current) {
    const p=session.current,t=trials[p.index];
    rows.push({order:p.index+1,item_id:t.item_id,block_id:t.block_id,...p.locked,target_match:null,play_count:p.playCount,completed_audio:p.heard,elapsed_s:p.elapsed_s,created_utc:p.created_utc});
  }
  return rows;
}
export function reconcileSession(session,remote) {
  if(remote.participant_id!==session.participant_id || remote.seed!==session.seed || remote.group!==session.group || remote.study_version!==session.study_version) throw new Error('The saved session has different allocation details.');
  for(let i=0;i<Math.min(session.rows.length,remote.rows.length);i++) {
    if(['item_id','block_id','valence','arousal','naturalness','target_match'].some(k=>session.rows[i][k]!==remote.rows[i][k])) throw new Error('The browser and server contain conflicting ratings. Keep your CSV and contact the researcher.');
  }
  if(remote.rows.length>session.rows.length) {session.rows=remote.rows;session.current=null;}
  if(remote.pending && remote.pending.trial_order===session.rows.length+1) {
    const p=remote.pending;
    if(session.current && ['valence','arousal','naturalness'].some(k=>session.current.locked[k]!==p[k])) throw new Error('Your saved initial ratings conflict. Keep your CSV and contact the researcher.');
    if(!session.current) session.current={index:p.trial_order-1,locked:{valence:p.valence,arousal:p.arousal,naturalness:p.naturalness},heard:Boolean(p.completed_audio),playCount:p.play_count,elapsed_s:p.elapsed_s,created_utc:p.created_utc};
  }
  session.remote.saved_count=remote.saved_count;
  return session;
}
export class StudySync {
  constructor({session,trials,fetcher=fetch,onStatus=()=>{}}) {Object.assign(this,{session,trials,fetcher,onStatus});this.registered=false;this.dirty=false;this.running=null;this.stopped=false;}
  async request(path,method='GET',data) {
    const controller=new AbortController(),timeout=setTimeout(()=>controller.abort(),15000);
    try {
      const response=await this.fetcher.call(globalThis,path,{method,headers:{'Content-Type':'application/json',Authorization:`Bearer ${this.session.remote.token}`},body:data?JSON.stringify(data):undefined,signal:controller.signal});
      const result=await response.json();
      if(!response.ok) {const error=new Error(result.error || 'The database did not accept these responses.');error.status=response.status;throw error;} return result;
    } finally {clearTimeout(timeout);}
  }
  async register() {
    const s=this.session;
    const result=await this.request('/api/study/sessions','POST',{participant_id:s.participant_id,nickname:s.nickname,rating_scale:s.rating_scale,study_version:s.study_version,collection_version:COLLECTION_VERSION,record_type:s.record_type,group:s.group,seed:s.seed,eligibility:s.eligibility,consent:true,consent_utc:s.remote.consent_utc,listener_id:s.listener_id??null,gender:s.gender??null});
    this.registered=true;return result;
  }
  // Playback events wait in the session and travel with the next save, so listening adds no requests of its own.
  playback(event) {
    this.session.playback||=[];this.session.playback_seq=(this.session.playback_seq||0)+1;
    this.session.playback.push({...event,seq:this.session.playback_seq});
  }
  // A playback failure never blocks or relabels the responses: events the server rejects are counted and dropped,
  // and unsent events wait for the next save.
  async sendPlayback() {
    try {
      while(this.session.playback?.length&&!this.stopped) {
        const batch=this.session.playback.slice(0,200);let received;
        try {received=(await this.request(`/api/study/sessions/${this.session.participant_id}/playback`,'POST',{events:batch})).received_event_ids;}
        catch(error) {if(error.status!==400)throw error;received=batch.map(e=>e.event_id);this.session.playback_rejected=(this.session.playback_rejected||0)+batch.length;}
        const done=new Set(received);this.session.playback=this.session.playback.filter(e=>!done.has(e.event_id));
      }
    } catch {}
  }
  async restore() {const result=await this.register();reconcileSession(this.session,result);return result;}
  sync() {
    if(this.stopped)return Promise.resolve();
    this.dirty=true;if(this.running)return this.running;
    this.running=this.drain().finally(()=>{this.running=null;});return this.running;
  }
  async drain() {
    try {
      while(this.dirty&&!this.stopped) {
        this.dirty=false;this.onStatus({state:'saving',saved:this.session.remote.saved_count || 0});
        if(!this.registered) await this.restore();
        const rows=wireRows(this.session,this.trials);
        const result=rows.length?await this.request(`/api/study/sessions/${this.session.participant_id}/responses`,'POST',{rows}):{saved_count:0};
        this.session.remote.saved_count=result.saved_count;
        await this.sendPlayback();
        this.onStatus({state:this.dirty?'saving':'saved',saved:result.saved_count});
      }
    } catch(error) {
      this.dirty=true;
      this.onStatus({state:[400,401,403,409,410].includes(error.status)?'conflict':'offline',saved:this.session.remote.saved_count || 0,message:error.message});
    }
  }
  async withdraw() {
    this.stopped=true;if(this.running)await this.running;
    // Registration also makes withdrawal retryable when the first registration response was lost.
    try {if(!this.registered)await this.register();} catch(error) {if(error.status===410)return {withdrawn:true};throw error;}
    return this.request(`/api/study/sessions/${this.session.participant_id}`,'DELETE');
  }
}
