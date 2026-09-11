import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {requestReply} from '../dialogue-client.js';

const input={text:'The meeting was moved to a different room.',emotion:'calm',history:[]};

test('the page client posts to the server route and surfaces its error text',async()=>{
  const calls=[];
  const fetchImpl=async(url,init)=>{calls.push({url,body:JSON.parse(init.body)});return {ok:true,json:async()=>({text:'Hello.',gate:'off'})};};
  assert.equal((await requestReply(input,{fetchImpl})).text,'Hello.');
  assert.deepEqual(calls,[{url:'/api/dialogue/reply',body:input}]);
  await assert.rejects(requestReply(input,{fetchImpl:async()=>({ok:false,json:async()=>({error:'Start Ollama.'})})}),/Start Ollama/);
  await assert.rejects(requestReply(input,{fetchImpl:async()=>({ok:false,json:async()=>{throw new Error('not json');}})}),/could not be generated/);
});

test('no page or frontend script names Qwen or loads the in-browser model',()=>{
  const files=['app.js','neural.worker.js','neural-client.js','dialogue-client.js','model-config.js','voice-controls.js','home.js','listen.js',
    'index.html','studio.html','listen.html','research.html','public/README.html','public/listener-instructions.html'];
  for(const file of files){
    const text=readFileSync(new URL(`../${file}`,import.meta.url),'utf8');
    assert.doesNotMatch(text,/qwen|web-?llm|@mlc-ai|mlc-chat|navigator\.gpu/i,`${file} still names or loads the in-browser model`);
  }
});
