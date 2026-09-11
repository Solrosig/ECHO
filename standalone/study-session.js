export const RATING_SCALE='va-0.01_match-0.5_naturalness-1_v2';
export function seededRandom(seed){let s=seed>>>0;return ()=>{s+=0x6D2B79F5;let t=s;t=Math.imul(t^t>>>15,t|1);t^=t+Math.imul(t^t>>>7,t|61);return ((t^t>>>14)>>>0)/4294967296;};}
export function makeTrials(manifest,group,seed){
 if(!Number.isInteger(group)||group<0||group>=manifest.groups.length)throw new Error('Invalid study group.');
 const selected=manifest.groups[group],map=new Map(manifest.blocks.map(b=>[b.block_id,b]));
 const trials=selected.flatMap(id=>{const block=map.get(id);return block.item_ids.map(item_id=>({item_id,block_id:id,target:block.target}));});
 if(new Set(trials.map(t=>t.item_id)).size!==trials.length)throw new Error('A listener must not rate the same waveform twice.');
 const random=seededRandom(seed);for(let i=trials.length-1;i>0;i--){const j=Math.floor(random()*(i+1));[trials[i],trials[j]]=[trials[j],trials[i]];}
 return trials;
}
export function validateRating(r){
 if(!['valence','arousal'].every(k=>Number.isFinite(r[k])&&r[k]>=-1&&r[k]<=1))throw new Error('Rate both emotional dimensions.');
 if(!Number.isInteger(r.naturalness)||r.naturalness<1||r.naturalness>5)throw new Error('Choose a naturalness rating.');
 if(!Number.isFinite(r.target_match)||!Number.isInteger(r.target_match*2)||r.target_match<1||r.target_match>5)throw new Error('Choose a target-match rating.');
}
export const CSV_FIELDS=['study_version','collection_version','rating_scale','record_type','participant_id','nickname','group','seed','order','item_id','audio_sha256','block_id','valence','arousal','naturalness','target_match','play_count','completed_audio','elapsed_s','created_utc','comfortable_english','headphones','previously_used_studio'];
export function rowsCSV(rows){return [CSV_FIELDS.join(','),...rows.map(r=>CSV_FIELDS.map(k=>`"${String(r[k]??'').replaceAll('"','""')}"`).join(','))].join('\r\n')+'\r\n';}
