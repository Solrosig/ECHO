import test from 'node:test';
import assert from 'node:assert/strict';
import {dialogueMessages,stripActLabel,DEFAULT_PROMPT,DIALOGUE_PROMPT_VERSION,EXAMPLE_MESSAGES} from '../server/dialogue-prompt.mjs';
import {REPLY_CHECK_VERSION,CHECK_GENERATION,CHECK_FORMAT,replyCheckMessages,parseVerdict,judgeReply,acceptedAttempt} from '../server/reply-check.mjs';
import {dialogueConfig,dialogueReply,handleDialogueRequest,GENERATION,DEFAULT_REPLY_CHECK} from '../server/dialogue.mjs';
import {REPLY_CHECK_COLUMNS,replyCheckColumns} from '../generation-timing.js';

const EMOTIONS=['happy','upset','sad','calm'];
const reply=content=>({ok:true,status:200,json:async()=>({choices:[{message:{content},finish_reason:'stop'}]})});
const verdict=(responds,feeling,energy)=>reply(JSON.stringify({responds,feeling,energy}));
// A stand-in for Ollama that answers each request from a queue and keeps the payloads it received.
function ollama(queue){const calls=[];return {calls,fetchImpl:async(_,init)=>{calls.push(JSON.parse(init.body));const next=queue.shift();if(!next)throw new Error('unexpected call');return next;}};}

test('v3 stays the default prompt; the v4 candidates add an answer-first rule and four examples',()=>{
  assert.equal(DEFAULT_PROMPT,'v3');assert.equal(DIALOGUE_PROMPT_VERSION,'echo-dialogue-v3');
  for(const emotion of EMOTIONS){
    const text='Hello, help me my friend',v3=dialogueMessages(text,emotion);
    assert.deepEqual(dialogueMessages(text,emotion,[],{variant:'v3'}),v3);
    assert.match(v3[0].content,/For example, to the message "It is supposed to rain tomorrow afternoon\."/);
    const a=dialogueMessages(text,emotion,[],{variant:'v4a'})[0].content,b=dialogueMessages(text,emotion,[],{variant:'v4b'})[0].content;
    for(const system of [a,b]){
      assert.match(system,/First respond to what the user actually said or asked/);
      for(const message of Object.values(EXAMPLE_MESSAGES))assert.ok(system.includes(`To "${message}"`));
      assert.doesNotMatch(system,/rain tomorrow/i);
    }
    assert.doesNotMatch(a,/one word on its own line/);assert.match(b,/one word on its own line/);
  }
  assert.throws(()=>dialogueMessages('Hi','happy',[],{variant:'v5'}),/Unknown conversation prompt/);
});

test('v4 examples follow each emotion\'s delivery cue and use no message from the screens',()=>{
  const screened=['Hello, help me my friend','Can you help me fix my bike?','Please help me, I lost my keys.','What should I cook for dinner tonight?','Hi there, how are you?','Good morning!','Help me prepare for a busy study day.'];
  for(const message of Object.values(EXAMPLE_MESSAGES))assert.ok(!screened.includes(message));
  for(const emotion of EMOTIONS){
    const lines=dialogueMessages('Hi',emotion,[],{variant:'v4a'})[0].content.split('\n').filter(line=>line.startsWith('To "'));
    assert.equal(lines.length,4);
    const replies=lines.map(line=>line.slice(line.indexOf('": "')+4,-1));
    if(emotion==='happy')assert.ok(replies.every(r=>r.includes('!')));
    if(['sad','calm'].includes(emotion))assert.ok(replies.every(r=>!r.includes('!')));
  }
});

test('the act word of a v4b reply is removed with its separator, and nothing else',()=>{
  assert.deepEqual(stripActLabel('request\nOf course, I can help.'),{reply:'Of course, I can help.',act:'request'});
  assert.deepEqual(stripActLabel('Question: Start with the dishes.'),{reply:'Start with the dishes.',act:'question'});
  assert.deepEqual(stripActLabel('**news**\n"Oh no, that is hard."'),{reply:'"Oh no, that is hard."',act:'news'});
  assert.deepEqual(stripActLabel('Greeting - Hi there!'),{reply:'Hi there!',act:'greeting'});
  assert.deepEqual(stripActLabel('Joke\nI\'ve got one! Why could the bicycle not stand up?'),{reply:'I\'ve got one! Why could the bicycle not stand up?',act:'joke'});
  for(const text of ['Other than that, it went well.','News travels fast!','request','Hi!\nHow are you?'])assert.deepEqual(stripActLabel(text),{reply:text,act:null});
});

test('the check reads a JSON verdict blind to the target, maps it to a quadrant and scores misses',()=>{
  assert.deepEqual(parseVerdict('{"responds":"yes","feeling":"Positive","energy":"low"}'),{responds:true,feeling:'positive',energy:'low'});
  assert.deepEqual(parseVerdict('Here: {"responds": "no", "feeling": "negative", "energy": "high"} done'),{responds:false,feeling:'negative',energy:'high'});
  for(const bad of ['','not json','{"responds":"maybe","feeling":"positive","energy":"low"}','{"responds":"yes","feeling":"positive"}',null])assert.equal(parseVerdict(bad),null);
  const passed=judgeReply({responds:true,feeling:'positive',energy:'low'},'calm'),energy=judgeReply({responds:true,feeling:'positive',energy:'high'},'calm'),neutral=judgeReply({responds:false,feeling:'neutral',energy:'low'},'sad');
  assert.deepEqual([passed.quadrant,passed.passed,passed.score],['calm',true,4]);
  assert.deepEqual([energy.quadrant,energy.passed,energy.score],['happy',false,3]);
  assert.deepEqual([neutral.quadrant,neutral.passed,neutral.score],[null,false,1]);
  assert.deepEqual(acceptedAttempt([{passed:false,score:3},{passed:true,score:4}]),{status:'passed',index:1});
  assert.deepEqual(acceptedAttempt([{passed:false,score:2},{passed:false,score:3},{passed:false,score:3}]),{status:'failed',index:1});
  assert.deepEqual(acceptedAttempt([{passed:false,score:3},null]),{status:'unavailable',index:1});
  const [system,user]=replyCheckMessages('Hi there, how are you?','Hi! I am great!',[{role:'user',content:'Hello'},{role:'assistant',content:'Hey!'}]);
  assert.doesNotMatch(system.content,/happy|upset|sad|calm/i);
  assert.equal(user.content,'User earlier: "Hello"\nReply earlier: "Hey!"\nUser\'s last message: "Hi there, how are you?"\nReply: "Hi! I am great!"');
});

test('with the check on, a reply that misses is generated again with the next seed until one passes',async()=>{
  const {calls,fetchImpl}=ollama([reply('That is very kind of you to offer.'),verdict('no','positive','low'),reply('Of course, tell me what you need help with.'),verdict('yes','positive','low')]);
  const out=await dialogueReply({text:'Hello, help me my friend',emotion:'calm',history:[]},dialogueConfig({ECHO_REPLY_CHECK:'on',ECHO_DIALOGUE_PROMPT:'v4a'}),{fetchImpl});
  assert.equal(out.text,'Of course, tell me what you need help with.');
  assert.deepEqual([out.prompt_version,out.check.version,out.check.status,out.check.attempts,out.check.accepted],['echo-dialogue-v4a','echo-reply-check-v1','passed',2,1]);
  assert.deepEqual(calls.map(c=>[c.seed,c.temperature,c.max_tokens,c.response_format?.type??null]),[[666,.7,150,null],[666,0,60,'json_object'],[667,.7,150,null],[666,0,60,'json_object']]);
  assert.deepEqual(out.check.verdicts.map(v=>[v.seed,v.quadrant,v.passed]),[[666,'calm',false],[667,'calm',true]]);
  assert.deepEqual(out.details.map(d=>d.text),['That is very kind of you to offer.','Of course, tell me what you need help with.']);
});

test('when every attempt misses the best one is used and flagged; an unreadable check accepts the reply; off changes nothing',async()=>{
  const on=dialogueConfig({ECHO_REPLY_CHECK:'on'}),input={text:'Can you help me fix my bike?',emotion:'calm'};
  let fake=ollama([reply('A'),verdict('no','negative','high'),reply('B'),verdict('yes','positive','high'),reply('C'),verdict('no','positive','low')]);
  let out=await dialogueReply(input,on,{fetchImpl:fake.fetchImpl});
  assert.deepEqual([out.text,out.check.status,out.check.attempts,out.check.accepted],['B','failed',3,1]);
  fake=ollama([reply('Fine.'),reply('I cannot answer that.')]);
  out=await dialogueReply(input,on,{fetchImpl:fake.fetchImpl});
  assert.deepEqual([out.text,out.check.status,out.check.attempts,out.check.verdicts],['Fine.','unavailable',1,[null]]);
  fake=ollama([reply('Fine.')]);
  out=await dialogueReply(input,dialogueConfig({}),{fetchImpl:fake.fetchImpl});
  assert.deepEqual(out,{text:'Fine.',gate:'off',prompt_version:'echo-dialogue-v3'});
  assert.equal(JSON.stringify(fake.calls[0]),JSON.stringify({model:'llama3.2:3b',messages:dialogueMessages(input.text,'calm'),...GENERATION,stream:false}));
});

test('a failed retry keeps the best earlier attempt, and the page never receives rejected texts',async()=>{
  const fake=ollama([reply('First try.'),verdict('yes','negative','low'),reply('')]),lines=[],json=(value,status=200)=>({status,value});
  const env={DIALOGUE:{config:dialogueConfig({ECHO_REPLY_CHECK:'on'}),log:e=>lines.push(e),fetch:fake.fetchImpl}};
  const res=await handleDialogueRequest({},env,{readBody:async()=>({text:'Please help me, I lost my keys.',emotion:'calm',history:[]}),json});
  assert.equal(res.status,200);assert.equal(res.value.text,'First try.');assert.equal(res.value.details,undefined);
  assert.deepEqual([res.value.check.status,res.value.check.attempts,res.value.check.verdicts[0].quadrant],['failed',1,'sad']);
  assert.deepEqual([lines[0].check.status,lines[0].check.replies,lines[0].prompt_version],['failed',['First try.'],'echo-dialogue-v3']);
});

test('reply-check settings are validated, and the saved check appears in the exploratory CSV columns',()=>{
  assert.equal(DEFAULT_REPLY_CHECK,'off');
  const config=dialogueConfig({});assert.deepEqual([config.prompt,config.check,config.checkRetries],['v3','off',2]);
  assert.throws(()=>dialogueConfig({ECHO_DIALOGUE_PROMPT:'v9'}),/ECHO_DIALOGUE_PROMPT/);
  assert.throws(()=>dialogueConfig({ECHO_REPLY_CHECK:'maybe'}),/ECHO_REPLY_CHECK must be/);
  assert.throws(()=>dialogueConfig({ECHO_REPLY_CHECK_RETRIES:'9'}),/ECHO_REPLY_CHECK_RETRIES/);
  assert.equal(REPLY_CHECK_VERSION,'echo-reply-check-v1');
  assert.deepEqual([CHECK_GENERATION,CHECK_FORMAT],[{temperature:0,seed:666,max_tokens:60},{type:'json_object'}]);
  assert.deepEqual(REPLY_CHECK_COLUMNS,['reply_prompt_version','reply_check_status','reply_check_attempts','reply_check_accepted']);
  assert.deepEqual(replyCheckColumns({dialogue:{prompt_version:'echo-dialogue-v4a',check:{status:'passed',attempts:2,accepted:1}}}),
    {reply_prompt_version:'echo-dialogue-v4a',reply_check_status:'passed',reply_check_attempts:2,reply_check_accepted:1});
});
