export function unduplicateEspeak(buffer){
  const doubled=new Float32Array(buffer);
  if(doubled.length%2)throw new Error('Unexpected eSpeak sample layout.');
  const mono=new Float32Array(doubled.length/2);
  for(let i=0;i<mono.length;i++){
    if(doubled[i*2]!==doubled[i*2+1])throw new Error('eSpeak sample layout differs from the pinned runtime.');
    mono[i]=doubled[i*2];
  }
  return mono;
}
export function audioResult(samples,sampleRate,gain){
  if(!samples.length||!Number.isFinite(sampleRate)||sampleRate<8000)throw new Error('No valid speech audio was returned.');
  const buffer=new ArrayBuffer(44+samples.length*2),view=new DataView(buffer);
  const write=(at,s)=>[...s].forEach((c,i)=>view.setUint8(at+i,c.charCodeAt(0)));
  write(0,'RIFF');view.setUint32(4,buffer.byteLength-8,true);write(8,'WAVE');write(12,'fmt ');
  view.setUint32(16,16,true);view.setUint16(20,1,true);view.setUint16(22,1,true);
  view.setUint32(24,sampleRate,true);view.setUint32(28,sampleRate*2,true);view.setUint16(32,2,true);view.setUint16(34,16,true);
  write(36,'data');view.setUint32(40,samples.length*2,true);
  let square=0,peak=0,clipped=0;const envelope=Array(64).fill(0);
  for(let i=0;i<samples.length;i++){
    const raw=samples[i]*gain;if(!Number.isFinite(raw))throw new Error('Invalid audio sample.');
    if(Math.abs(raw)>1)clipped++;const s=Math.max(-1,Math.min(1,raw));
    square+=s*s;peak=Math.max(peak,Math.abs(s));envelope[Math.min(63,Math.floor(i/samples.length*64))]=Math.max(envelope[Math.min(63,Math.floor(i/samples.length*64))],Math.abs(s));
    view.setInt16(44+i*2,Math.round(s*(s<0?32768:32767)),true);
  }
  return {buffer,sample_rate:sampleRate,duration_s:samples.length/sampleRate,rms:Math.sqrt(square/samples.length),peak,clipped_samples:clipped,envelope};
}
export async function hashAudio(buffer){return Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',buffer)),x=>x.toString(16).padStart(2,'0')).join('');}
