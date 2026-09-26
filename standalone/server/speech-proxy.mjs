import {Readable} from 'node:stream';

// Fixed, administrator-configured upstream: callers cannot choose a server or forward credentials. Only this proxy adds
// the administrator token (ECHO_TTS_TOKEN); on Hugging Face it makes ZeroGPU bill the Space owner, not the visitor. The
// relay key (ECHO_TTS_RELAY_KEY) tells the Space that the request comes from this server.
export async function proxySpeech(req,res,url,origin,upstream,token=null,relayKey=null){
 if(!['GET','POST','HEAD'].includes(req.method)){res.writeHead(405);res.end();return;}
 if(req.headers.origin&&req.headers.origin!==origin||req.headers['sec-fetch-site']==='cross-site'){res.writeHead(403);res.end('Use the ECHO website.');return;}
 const suffix=url.pathname.slice('/api/tts'.length)||'/';
 if(!/^\/(?:config|info|gradio_api(?:\/(?:info|queue\/(?:join|data)|cancel|reset|heartbeat|file=.*))?)?\/?$/.test(suffix)){res.writeHead(404);res.end();return;}
 const target=new URL(upstream);target.pathname=target.pathname.replace(/\/$/,'')+suffix;target.search=url.search;
 const headers={'accept':req.headers.accept||'*/*','host':new URL(origin).host,'x-forwarded-host':new URL(origin).host,'x-forwarded-proto':new URL(origin).protocol.slice(0,-1)};
 if(token)headers.authorization=`Bearer ${token}`;
 if(relayKey)headers['x-echo-voice-relay']=relayKey;
 if(req.headers['content-type'])headers['content-type']=req.headers['content-type'];
 if(req.headers.range)headers.range=req.headers.range;
 const abort=new AbortController();res.on('close',()=>abort.abort());
 try{
  let body;
  if(req.method==='POST'){const chunks=[];let size=0;for await(const chunk of req){size+=chunk.length;if(size>16384){res.writeHead(413);res.end();return;}chunks.push(chunk);}body=Buffer.concat(chunks);}
  const response=await fetch(target,{method:req.method,headers,body,signal:abort.signal,redirect:'error'});
  const output={'Cache-Control':'no-store'};
  for(const name of ['content-type','content-range','accept-ranges'])if(response.headers.has(name))output[name]=response.headers.get(name);
  res.writeHead(response.status,output);
  if(!response.body||req.method==='HEAD'){res.end();return;}
  Readable.fromWeb(response.body).on('error',()=>res.destroy()).pipe(res);
 }catch(error){if(res.destroyed)return;if(!res.headersSent)res.writeHead(503,{'Content-Type':'application/json'});res.end(JSON.stringify({error:'The speech service is not reachable. Start tts-service/app.py, or set ECHO_TTS_URL to its address.'}));}
}
