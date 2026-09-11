// IndexedDB is a retry queue; the server archive remains the durable research record.
function database(){return new Promise((resolve,reject)=>{if(!globalThis.indexedDB)return reject(new Error('Audio browser backup unavailable.'));const r=indexedDB.open('echo-audio-outbox-v1',1);r.onupgradeneeded=()=>r.result.createObjectStore('audio');r.onsuccess=()=>resolve(r.result);r.onerror=()=>reject(r.error);});}
async function transaction(mode,operation){const db=await database();try{return await new Promise((resolve,reject)=>{const tx=db.transaction('audio',mode),r=operation(tx.objectStore('audio'));let result;r.onsuccess=()=>{result=r.result;};tx.oncomplete=()=>resolve(result);tx.onerror=()=>reject(tx.error);tx.onabort=()=>reject(tx.error||new Error('Audio backup interrupted.'));});}finally{db.close();}}
export const savePendingAudio=(key,buffer)=>transaction('readwrite',s=>s.put(buffer,key));
export const loadPendingAudio=key=>transaction('readonly',s=>s.get(key));
export const deletePendingAudio=key=>transaction('readwrite',s=>s.delete(key));
