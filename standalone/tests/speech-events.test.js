import test from 'node:test';import assert from 'node:assert/strict';import {collectSpeechResult} from '../speech-events.js';
test('returns the WAV on explicit completion even when the Gradio iterator stays open',async()=>{
 const events=[{type:'status',stage:'pending'},{type:'data',data:[{url:'http://localhost/example.wav'},{engine:'parlertts'}]},{type:'status',stage:'complete'}];let reads=0;
 const job={[Symbol.asyncIterator](){return {return(){throw Error('Do not await Gradio iterator.return()');},next(){reads++;if(!events.length)throw Error('Read past completion');return Promise.resolve({done:false,value:events.shift()});}};}};
 const result=await collectSpeechResult(job);assert.equal(result[1].engine,'parlertts');assert.equal(reads,3);
});
test('a failed server job is surfaced without waiting for stream closure',async()=>{
 async function* failed(){yield {type:'status',stage:'error',message:'GPU quota exceeded'};throw Error('Read past error');}
 await assert.rejects(collectSpeechResult(failed()),/GPU quota exceeded/);
});
test('cancellation does not return a late result',async()=>{
 async function* late(){yield {type:'data',data:['late']};}
 await assert.rejects(collectSpeechResult(late(),()=>{},()=>true),/cancelled/);
});

