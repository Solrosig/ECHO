// Exact generated WAVs are private research assets. The caller has already authenticated.
const MAX_BYTES=12*1024*1024;
// Default cap on archived WAV bytes across all sessions; the Node server sets it from ECHO_AUDIO_QUOTA_MB.
const DEFAULT_QUOTA_BYTES=2048*1024*1024;
export const audioKey=(session,order,sha)=>`interactive/${session}/${order}-${sha}.wav`;
export function wavInfo(buffer){
 const v=new DataView(buffer),word=(p,n)=>Array.from({length:n},(_,i)=>String.fromCharCode(v.getUint8(p+i))).join('');
 if(v.byteLength<44||word(0,4)!=='RIFF'||word(8,4)!=='WAVE'||v.getUint32(4,true)+8!==v.byteLength)throw new Error('Invalid WAV file.');
 let format,bytes;
 for(let at=12;at+8<=v.byteLength;){const kind=word(at,4),n=v.getUint32(at+4,true),start=at+8;if(start+n>v.byteLength)throw new Error('Incomplete WAV data.');
  if(kind==='fmt '){if(n<16)throw new Error('Invalid WAV format.');format={codec:v.getUint16(start,true),channels:v.getUint16(start+2,true),sample_rate:v.getUint32(start+4,true),byte_rate:v.getUint32(start+8,true),block_align:v.getUint16(start+12,true),bits:v.getUint16(start+14,true)};}
  if(kind==='data'){if(bytes!==undefined)throw new Error('Ambiguous WAV data.');bytes=n;}
  at=start+n+(n%2);
 }
 if(!format||format.codec!==1||format.channels!==1||format.bits!==16||format.block_align!==2||format.byte_rate!==format.sample_rate*2||!Number.isInteger(format.sample_rate)||format.sample_rate<8000||format.sample_rate>96000||!bytes||bytes%2)throw new Error('Expected mono PCM16 speech.');
 return {...format,duration_s:bytes/(format.sample_rate*2),byte_length:v.byteLength};
}
async function readWav(request,fail){
 if(!request.headers.get('content-type')?.startsWith('audio/wav'))fail(415,'Send a WAV recording.');
 const reader=request.body?.getReader();if(!reader)fail(400,'Missing audio.');const chunks=[];let n=0;
 for(;;){const {done,value}=await reader.read();if(done)break;n+=value.length;if(n>MAX_BYTES){await reader.cancel();fail(413,'The recording exceeds 12 MiB.');}chunks.push(value);}
 const data=new Uint8Array(n);let offset=0;for(const c of chunks){data.set(c,offset);offset+=c.length;}return data.buffer;
}
export async function audioDownload(db,bucket,session,order,fail){
 if(!bucket)fail(503,'Audio storage is unavailable.');
 const r=await db.prepare('SELECT a.* FROM interactive_audio a JOIN interactive_sessions s ON s.session_id=a.session_id WHERE a.session_id=? AND a.turn_order=? AND s.withdrawn_utc IS NULL').bind(session,order).first();
 if(!r)fail(404,'No archived recording for this message.');const object=await bucket.get(r.object_key);if(!object)fail(404,'The archived recording is unavailable.');
 return new Response(object.body,{headers:{'Content-Type':'audio/wav','Content-Disposition':`attachment; filename="echo-${session}-${order}.wav"`,'Cache-Control':'private, no-store','X-Content-Type-Options':'nosniff','X-Audio-SHA256':r.sha256}});
}
export async function audioUpload(request,h,s,order){
 const {db,audioBucket:bucket,fail,json,now}=h;if(!bucket)fail(503,'Audio storage is unavailable; keep this page open and retry saving.');
 const turn=await db.prepare('SELECT turn_json FROM interactive_turns WHERE session_id=? AND turn_order=?').bind(s.session_id,order).first();if(!turn)fail(404,'Save the message before its recording.');
 const meta=JSON.parse(turn.turn_json),buffer=await readWav(request,fail);let info;try{info=wavInfo(buffer);}catch(e){fail(400,e.message);}
 const hash=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',buffer)),x=>x.toString(16).padStart(2,'0')).join('');
 if(hash!==meta.audio_sha256)fail(409,'This audio does not match the saved message.');
 if(Math.abs(info.duration_s-meta.duration_s)>Math.max(.01,2/info.sample_rate))fail(409,'The recording duration does not match the message.');
 const archived=await db.prepare('SELECT sha256 FROM interactive_audio WHERE session_id=? AND turn_order=?').bind(s.session_id,order).first();
 if(!archived){const used=await db.prepare('SELECT COALESCE(SUM(byte_length),0) AS n FROM interactive_audio').first();if(used.n+info.byte_length>(h.audioQuotaBytes??DEFAULT_QUOTA_BYTES))fail(507,'The recording archive is full. The message stays saved without its recording; tell the researcher.');}
 const key=audioKey(s.session_id,order,hash),stamp=now();await bucket.put(key,buffer,{httpMetadata:{contentType:'audio/wav'},customMetadata:{sha256:hash}});
 const active=await db.prepare('SELECT withdrawn_utc FROM interactive_sessions WHERE session_id=?').bind(s.session_id).first();
 if(!active||active.withdrawn_utc){await bucket.delete(key);fail(410,'This contribution was deleted.');}
 await db.prepare('INSERT INTO interactive_audio (session_id,turn_order,sha256,object_key,byte_length,sample_rate,duration_s,stored_utc) SELECT ?,?,?,?,?,?,?,? WHERE EXISTS (SELECT 1 FROM interactive_sessions WHERE session_id=? AND withdrawn_utc IS NULL) ON CONFLICT(session_id,turn_order) DO NOTHING').bind(s.session_id,order,hash,key,info.byte_length,info.sample_rate,info.duration_s,stamp,s.session_id).run();
 const stored=await db.prepare('SELECT sha256 FROM interactive_audio WHERE session_id=? AND turn_order=?').bind(s.session_id,order).first();
 if(!stored){await bucket.delete(key);fail(410,'This contribution was deleted.');}
 if(stored.sha256!==hash)fail(409,'An archived recording cannot be overwritten.');
 return json({order,sha256:hash,archived:true,byte_length:info.byte_length});
}
export async function deleteSessionAudio(db,bucket,session){
 const rows=(await db.prepare('SELECT object_key FROM interactive_audio WHERE session_id=?').bind(session).all()).results;
 if(rows.length&&!bucket)throw new Error('Audio storage unavailable for withdrawal.');
 for(const row of rows)await bucket.delete(row.object_key);
 await db.prepare('DELETE FROM interactive_audio WHERE session_id=?').bind(session).run();
}
