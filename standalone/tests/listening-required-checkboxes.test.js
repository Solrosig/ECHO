import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';

const read = path => readFileSync(new URL('../'+path, import.meta.url), 'utf8');
const MARK = '<span class="required-mark" aria-hidden="true">*</span>';

test('the consent and English checkboxes are mandatory and carry a red asterisk (author, 2026-09-15)', () => {
  const listen = read('listen.html');
  assert.ok(listen.includes('<input id="consent" type="checkbox" required> I am 18 or older'));
  assert.ok(listen.includes('and responses stored for the thesis study.' + MARK + '</label>'));
  assert.ok(listen.includes('<input id="english" type="checkbox" required> I can comfortably understand spoken English.' + MARK + '</label>'));
  assert.equal(listen.split(MARK).length - 1, 2);
  assert.match(read('listen.css'), /\.required-mark\{color:#c62828;/);
});

test('no entry checkbox is ticked when the Listening page opens', () => {
  const listen = read('listen.html');
  const form = listen.match(/<form id="start-form"[\s\S]*?<\/form>/)[0];
  assert.ok(form.startsWith('<form id="start-form" autocomplete="off">'));
  for (const box of form.match(/<input[^>]*type="checkbox"[^>]*>/g)) assert.doesNotMatch(box, /\bchecked\b/, box);
  const app = read('listen.js');
  assert.doesNotMatch(app, /\$\('previous-studio'\)\.checked=wasExposed\(\)/);
  assert.match(app, /function clearEntryChecks\(\)\{for\(const id of \['consent','english','headphones','previous-studio'\]\)\$\(id\)\.checked=false;\}/);
  assert.match(app, /addEventListener\('pageshow',event=>\{if\(event\.persisted&&!\$\('setup'\)\.hidden\)clearEntryChecks\(\);\}\)/);
  // The saved record still notes earlier Test Mode or Explore Mode use.
  assert.match(app, /previously_used_studio:\$\('previous-studio'\)\.checked\|\|wasExposed\(\)/);
});
