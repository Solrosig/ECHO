import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';

const read = path => readFileSync(new URL('../'+path, import.meta.url), 'utf8');
const HINT = 'Write your first name and a nickname, e.g. anna_river. This helps avoid duplicates.';

test('every nickname field asks for a first name and a nickname, and the privacy wording says so', () => {
  for (const page of ['index.html', 'listen.html', 'studio.html']) {
    const html = read(page);
    assert.ok(html.includes(HINT), page);
    assert.ok(html.includes('placeholder="e.g. anna_river"'), page);
    assert.doesNotMatch(html, /not your real name|Use an alias|Choose an alias|listener_07/, page);
  }
  for (const page of ['listen.html', 'studio.html']) assert.match(read(page), /nickname \(which includes (my|your) first name\)/, page);
  const guide = read('public/listener-instructions.html');
  assert.match(guide, /enter your first name and a nickname in “Your nickname”/);
  assert.doesNotMatch(guide, /real name|enter an alias/);
});
