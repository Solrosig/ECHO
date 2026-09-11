// In-memory sliding-window limits for one server process; a restart clears them.
export function createLimiter({limit,windowMs,clock=Date.now,maxKeys=10000}){
  const hits=new Map();
  return key=>{
    const now=clock(),since=now-windowMs;
    if(!hits.has(key)&&hits.size>=maxKeys)for(const [k,times] of hits)if(times.at(-1)<=since)hits.delete(k);
    const recent=(hits.get(key)||[]).filter(time=>time>since);
    if(recent.length>=limit||!hits.has(key)&&hits.size>=maxKeys)return false;
    recent.push(now);hits.set(key,recent);return true;
  };
}
