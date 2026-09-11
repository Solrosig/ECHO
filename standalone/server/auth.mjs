import {randomBytes,scryptSync,timingSafeEqual,createHash} from 'node:crypto';
import {readFileSync,writeFileSync,mkdirSync,existsSync} from 'node:fs';
import {join} from 'node:path';
const digest=value=>createHash('sha256').update(value).digest('hex');
export function setPassword(dataDir,password,{replace=false}={}) {
  if(typeof password!=='string'||password.length<16||password.length>256)throw new Error('Use a password of 16–256 characters.');
  mkdirSync(dataDir,{recursive:true,mode:0o700});const file=join(dataDir,'researcher.json');
  if(existsSync(file)&&!replace)throw new Error('Researcher access already exists. Use --reset to replace it.');
  const salt=randomBytes(32).toString('hex'),hash=scryptSync(password,salt,64).toString('hex');
  writeFileSync(file,JSON.stringify({version:1,salt,hash},null,2)+'\n',{mode:0o600,flag:replace?'w':'wx'});
}
export function createAuth(dataDir,{clock=Date.now,secure=false}={}) {
  const file=join(dataDir,'researcher.json');
  if(!existsSync(file))throw new Error('Run node scripts/setup.mjs before starting ECHO.');
  let stored=readFileSync(file,'utf8');const sessions=new Map(),attempts=new Map(),ttl=8*60*60*1000;
  const cookieName='echo_research_session';
  const cookie=(token,age)=>`${cookieName}=${token}; Path=/; HttpOnly; SameSite=Strict; Max-Age=${age}${secure?'; Secure':''}`;
  function reload(){const next=readFileSync(file,'utf8');if(next!==stored){stored=next;sessions.clear();attempts.clear();}return JSON.parse(stored);}
  function prune(){const time=clock();for(const [k,v]of sessions)if(v<=time)sessions.delete(k);for(const [k,v]of attempts)if(v.until<=time)attempts.delete(k);}
  function token(request){const value=request.headers.get('cookie')?.split(';').map(v=>v.trim()).find(v=>v.startsWith(cookieName+'='))?.slice(cookieName.length+1);return /^[a-f0-9]{64}$/.test(value||'')?value:null;}
  return {
    authorised(request){reload();prune();const t=token(request);return Boolean(t&&sessions.has(digest(t)));},
    login(password,ip){const credentials=reload();prune();const time=clock();
      const history=attempts.get(ip)||{count:0,until:time+15*60*1000};
      if(history.count>=5||attempts.size>=10000&&!attempts.has(ip))return {status:429,error:'Too many attempts. Wait 15 minutes.'};
      history.count++;attempts.set(ip,history);
      const valid=typeof password==='string'&&password.length>=16&&password.length<=256;
      const candidate=scryptSync(valid?password:'invalid',credentials.salt,64);
      if(!valid||!timingSafeEqual(candidate,Buffer.from(credentials.hash,'hex')))return {status:401,error:'Incorrect researcher password.'};
      attempts.delete(ip);if(sessions.size>=1000)return {status:429,error:'Too many active researcher sessions.'};
      const value=randomBytes(32).toString('hex');sessions.set(digest(value),time+ttl);
      return {status:200,cookie:cookie(value,ttl/1000)};
    },
    logout(request){const t=token(request);if(t)sessions.delete(digest(t));return cookie('',0);}
  };
}
