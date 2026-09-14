import test from 'node:test';
import assert from 'node:assert/strict';
import {dialogueMessages,rewriteMessages,PROMPT_VERSIONS} from '../server/dialogue-prompt.mjs';
import {dialogueConfig,dialogueReply,handleDialogueRequest,GENERATION} from '../server/dialogue.mjs';

const reply=content=>({ok:true,status:200,json:async()=>({choices:[{message:{content},finish_reason:'stop'}]})});
function ollama(queue){const calls=[];return {calls,fetchImpl:async(_,init)=>{calls.push(JSON.parse(init.body));const next=queue.shift();if(!next)throw new Error('unexpected call');return next;}};}

test('v4c writes a plain first pass without the emotion, then a rewrite into the chosen emotion',()=>{
  assert.equal(PROMPT_VERSIONS.v4c,'echo-dialogue-v4c');
  const history=[{role:'user',content:'Can you help me with something?'},{role:'assistant',content:'Of course. What do you need?'}];
  const draft=dialogueMessages('My phone won\'t charge anymore.','sad',history,{variant:'v4c'});
  assert.match(draft[0].content,/Respond to what the user actually said or asked/);
  assert.doesNotMatch(draft[0].content,/HAPPY|UPSET|SAD|CALM|emotion/);
  assert.deepEqual(draft.slice(1),[...history,{role:'user',content:'My phone won\'t charge anymore.'}]);
  assert.deepEqual(dialogueMessages('Hi','happy',[],{variant:'v4c'})[0],dialogueMessages('Hi','sad',[],{variant:'v4c'})[0]);
  const [system,user]=rewriteMessages('Help me prepare for a busy study day.','Start with the hardest topic, then take short breaks.','sad');
  assert.match(system.content,/SAD and SUBDUED \(negative feeling, low energy\)/);
  assert.match(system.content,/Keep what the reply says/);
  assert.match(system.content,/without exclamation marks/);
  assert.match(system.content,/the sofa on Saturday/);
  assert.equal(user.content,'User\'s message: "Help me prepare for a busy study day."\nReply to rewrite: "Start with the hardest topic, then take short breaks."');
  assert.throws(()=>rewriteMessages('Hi','','calm'),/no reply to rewrite/);
  assert.throws(()=>rewriteMessages('Hi','Hello.','angry'),/Choose an emotion/);
});

test('a v4c reply takes two calls with the same seed; the draft stays in the private metrics',async()=>{
  const fake=ollama([reply('Sure, tell me what is wrong with the bike.'),reply('"Ugh, bikes break at the worst time. Tell me what is wrong with it!"')]);
  const lines=[],json=(value,status=200)=>({status,value});
  const env={DIALOGUE:{config:dialogueConfig({ECHO_DIALOGUE_PROMPT:'v4c'}),log:e=>lines.push(e),fetch:fake.fetchImpl}};
  const res=await handleDialogueRequest({},env,{readBody:async()=>({text:'Can you help me fix my bike?',emotion:'upset',history:[]}),json});
  assert.deepEqual(res,{status:200,value:{text:'Ugh, bikes break at the worst time. Tell me what is wrong with it!',gate:'off',prompt_version:'echo-dialogue-v4c'}});
  assert.equal(fake.calls.length,2);
  assert.deepEqual(fake.calls.map(c=>[c.seed,c.temperature,c.max_tokens]),[[666,.7,150],[666,.7,150]]);
  assert.equal(JSON.stringify(fake.calls[0]),JSON.stringify({model:'llama3.2:3b',messages:dialogueMessages('Can you help me fix my bike?','upset',[],{variant:'v4c'}),...GENERATION,stream:false}));
  assert.match(fake.calls[1].messages[1].content,/Reply to rewrite: "Sure, tell me what is wrong with the bike\."/);
  assert.deepEqual([lines[0].prompt_version,lines[0].drafts],['echo-dialogue-v4c',['Sure, tell me what is wrong with the bike.']]);
});

test('an empty v4c draft is refused like an empty reply, and the coherence gate cannot run v4c',async()=>{
  const fake=ollama([reply('')]);
  await assert.rejects(dialogueReply({text:'Hello, help me my friend',emotion:'calm'},dialogueConfig({ECHO_DIALOGUE_PROMPT:'v4c'}),{fetchImpl:fake.fetchImpl}),e=>e.status===502);
  assert.equal(fake.calls.length,1);
  assert.throws(()=>dialogueConfig({ECHO_DIALOGUE_PROMPT:'v4c',ECHO_COHERENCE_GATE:'on'}),/cannot run the two-pass prompt/);
});

test('with the reply check on, each v4c attempt is checked after its rewrite',async()=>{
  const verdict=(responds,feeling,energy)=>reply(JSON.stringify({responds,feeling,energy}));
  const fake=ollama([reply('I can help with your keys.'),reply('I can help with your keys, though today feels heavy.'),verdict('yes','negative','low')]);
  const out=await dialogueReply({text:'Please help me, I lost my keys.',emotion:'sad',history:[]},dialogueConfig({ECHO_DIALOGUE_PROMPT:'v4c',ECHO_REPLY_CHECK:'on'}),{fetchImpl:fake.fetchImpl});
  assert.deepEqual([out.text,out.check.status,out.check.attempts],['I can help with your keys, though today feels heavy.','passed',1]);
  assert.equal(out.details[0].draft,'I can help with your keys.');
});
