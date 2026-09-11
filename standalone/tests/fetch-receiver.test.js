import test from 'node:test';
import assert from 'node:assert/strict';
import {StudySync} from '../study-sync.js';
import {InteractiveSync} from '../interactive-sync.js';

// Chromium native fetch rejects an instance receiver. Exercise the request boundary.
function browserLikeFetch() {
  assert.equal(this,globalThis,'fetch must retain the browser global receiver');
  return Promise.resolve(new Response(JSON.stringify({ok:true}),{status:200}));
}
test('Listening sync retains the native browser fetch receiver',async()=>{
  const client=new StudySync({session:{remote:{token:'technical-test'}},trials:[],fetcher:browserLikeFetch});
  assert.deepEqual(await client.request('/api/test'),{ok:true});
});
test('Interactive sync retains the native browser fetch receiver',async()=>{
  const client=new InteractiveSync({token:'technical-test'},{fetcher:browserLikeFetch});
  assert.deepEqual(await client.request('/api/test',{}),{ok:true});
});
