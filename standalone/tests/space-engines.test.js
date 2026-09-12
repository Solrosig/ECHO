import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {TEST_ENGINES,EXPLORE_ENGINES} from '../engine-catalog.js';

test('the Hugging Face Space loads exactly the server voices the website offers',()=>{
  const app=readFileSync(new URL('../deployment/huggingface/app.py',import.meta.url),'utf8');
  const loaded=JSON.parse(app.match(/^SITE_ENGINES=(\[[^\]]*\])/m)[1].replaceAll("'",'"'));
  const offered=[...new Set([...TEST_ENGINES,...EXPLORE_ENGINES])].filter(engine=>engine!=='kokoro');
  assert.deepEqual([...loaded].sort(),[...offered].sort());
});
