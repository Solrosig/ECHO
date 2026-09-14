import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';

const read = path => readFileSync(new URL('../'+path, import.meta.url), 'utf8');

test('the saved-session panel offers a confirmed new session with a new participant code', () => {
  const resume = read('listen.html').match(/<section id="resume"[\s\S]*?<\/section>/)[0];
  assert.match(resume, /<button id="restart-session" type="button" class="text-button">Start a new session<\/button>/);
  assert.match(resume, /<div id="restart-confirm" hidden>[\s\S]*stays saved as incomplete[\s\S]*<button id="restart-yes"[^>]*>Start a new session<\/button><button id="restart-cancel"[^>]*>Keep this session<\/button><\/div>/);
});

test('starting again keeps the unfinished session: it is synced, backed up if unconfirmed, and never withdrawn', () => {
  const listen = read('listen.js');
  const handler = listen.slice(listen.indexOf("$('restart-yes')"), listen.indexOf("$('new-session')"));
  assert.match(handler, /await syncClient\.sync\(\)/);
  assert.match(handler, /if\(!confirmed&&session\.rows\.length\)download\(\)/);
  assert.match(handler, /localStorage\.removeItem\(storageKey\)/);
  assert.match(handler, /panels\('setup'\)/);
  assert.doesNotMatch(handler, /withdraw|DELETE/);
  assert.match(read('public/listener-instructions.html'), /Continue session/);
});
