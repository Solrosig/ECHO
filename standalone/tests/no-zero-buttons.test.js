import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';

const read = path => readFileSync(new URL('../'+path, import.meta.url), 'utf8');

test('valence and arousal have no zero buttons on any page; the 1–5 midpoint buttons stay', () => {
  for (const file of ['listen.html', 'listen.js', 'message-rating-ui.js', 'public/listener-instructions.html']) {
    assert.doesNotMatch(read(file), /Choose neutral \(0\)|Choose moderate \(0\)|neutral-valence|neutral-arousal|'neutral-'\+key/, file);
  }
  assert.match(read('message-rating-ui.js'), /'Choose midpoint \(3\)'/);
  assert.match(read('listen.html'), /id="moderate-match"/);
});
