import test from 'node:test';import assert from 'node:assert/strict';import {createServer} from 'node:http';import {once} from 'node:events';import {proxySpeech} from '../server/speech-proxy.mjs';
test('speech proxy streams responses and strips researcher credentials',async t=>{
 let received;
 const upstream=createServer((req,res)=>{received=req.headers;res.setHeader('Content-Type','text/event-stream');res.write('data: first\n\n');setTimeout(()=>res.end('data: done\n\n'),10);});upstream.listen(0,'127.0.0.1');await once(upstream,'listening');
 const proxy=createServer((req,res)=>{const origin=`http://127.0.0.1:${proxy.address().port}`;return proxySpeech(req,res,new URL(req.url,origin),origin,`http://127.0.0.1:${upstream.address().port}`);});proxy.listen(0,'127.0.0.1');await once(proxy,'listening');
 t.after(()=>{proxy.closeAllConnections();proxy.close();upstream.closeAllConnections();upstream.close();});
 const base=`http://127.0.0.1:${proxy.address().port}`;
 const result=await fetch(base+'/api/tts/gradio_api/queue/data?session_hash=fixture',{headers:{Cookie:'researcher=private',Authorization:'Bearer private',Origin:base}});
 assert.equal(result.status,200);assert.match(result.headers.get('content-type'),/event-stream/);assert.equal(await result.text(),'data: first\n\ndata: done\n\n');assert.equal(received['x-forwarded-host'],new URL(base).host);assert.equal(received.cookie,undefined);assert.equal(received.authorization,undefined);
 assert.equal((await fetch(base+'/api/tts/gradio_api/queue/join',{method:'POST',headers:{Origin:'https://unrelated.example'},body:'{}'})).status,403);
 assert.equal((await fetch(base+'/api/tts/gradio_api/upload',{method:'POST',headers:{Origin:base},body:'{}'})).status,404);
});
