import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync, mkdtempSync, rmSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {once} from 'node:events';
import {renderFrontendVisibility} from '../frontend-visibility-build.js';
import {createEchoServer} from '../server/start.mjs';
import {setPassword} from '../server/auth.mjs';
import {SHOW_RESEARCH_PAGE} from '../frontend-visibility.js';

const read = path => readFileSync(new URL('../'+path, import.meta.url), 'utf8');
test('visibility flags independently restore complete section content and navigation', () => {
  const source = read('studio.html');
  const originalSection = source.match(/<section id="mechanisms"[\s\S]*?<\/section>/)[0];
  for (const engines of [false,true]) for (const research of [false,true]) {
    const flags = {SHOW_ENGINE_CONTROLS_SECTION:engines, SHOW_RESEARCH_PAGE:research};
    const html = renderFrontendVisibility(source,flags);
    assert.equal(html.includes(originalSection),engines);
    assert.equal(html.includes('href="#mechanisms"'),engines);
    assert.equal(html.includes('href="#research"'),research);
    assert.ok(html.includes('<section id="research"'));
    assert.ok(html.includes('<p class="small">Free hosting has queues and daily GPU limits.</p>'));
    for (const name of ['index.html','public/README.html','research.html']) {
      assert.equal(renderFrontendVisibility(read(name),flags).includes('href="/research"'),research,name);
    }
    assert.equal(renderFrontendVisibility(read('public/README.html'),{...flags,SHOW_RESEARCH_PAGE:true}),read('public/README.html'));
  }
});

test('requested copy, hero semantics and accessible acronym survive the production build', () => {
  const studio = read('dist/client/studio.html'), home = read('dist/client/index.html');
  const headline = 'Explore how a voice carries your chosen emotion. Hear the words through different TTS engines.';
  assert.ok(studio.includes('<h1>'+headline+'</h1>'));
  for (const old of ['You choose the feeling','Speak any English phrase','Say something. ECHO replies','Future work: an LLM could propose','Neural speech other than Kokoro','Hear the same words through different TTS engines.']) assert.ok(!studio.includes(old),old);
  assert.ok(studio.includes('Write any English phrase'));
  assert.ok(studio.includes('Write in the chat. ECHO replies'));
  assert.ok(home.includes('href="/README.html">Project guide</a>'));
  assert.ok(home.includes('aria-label="ECHO - Emotionally Coherent Conversational system"'));
  assert.ok(home.includes('<strong>E</strong>motionally <strong>C</strong>o<strong>H</strong>erent c<strong>O</strong>nversational system'));
  assert.ok(!home.includes('Academic voice research'));
});

test('research visibility guards both direct HTML and friendly routes, leaving APIs protected', async t => {
  const dataDir = mkdtempSync(join(tmpdir(),'echo-frontend-'));
  setPassword(dataDir,'frontend-test-password-12345');
  const server = createEchoServer({dataDir});
  server.listen(0,'127.0.0.1');await once(server,'listening');
  t.after(async()=>{await new Promise(resolve=>{server.close(resolve);server.closeAllConnections();});rmSync(dataDir,{recursive:true,force:true});});
  const origin = `http://127.0.0.1:${server.address().port}`;
  for (const path of ['/research','/research.html','/research?from=nav','/%72esearch']) {
    const response = await fetch(origin+path,{redirect:'manual'});
    assert.equal(response.status,SHOW_RESEARCH_PAGE?200:302,path);
    if (!SHOW_RESEARCH_PAGE) {assert.equal(response.headers.get('location'),'/');assert.equal(response.headers.get('cache-control'),'no-store');}
    else assert.match(await response.text(),/Listening study results/);
  }
  if (!SHOW_RESEARCH_PAGE) for (const path of ['/research/','/research.html/']) assert.equal((await fetch(origin+path,{redirect:'manual'})).status,302);
  const home = await fetch(origin+'/');assert.equal(home.status,200);
  assert.equal((await fetch(origin+'/api/research/summary')).status,401);
});
