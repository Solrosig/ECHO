import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';

const read = path => readFileSync(new URL('../'+path, import.meta.url), 'utf8');

test('no rating scale has a zero or midpoint shortcut button on any page', () => {
  for (const file of ['listen.html', 'listen.js', 'message-rating-ui.js', 'public/listener-instructions.html']) {
    assert.doesNotMatch(read(file), /Choose neutral \(0\)|Choose moderate \(0\)|Choose midpoint \(3\)|Choose moderately \(3\)|neutral-valence|neutral-arousal|moderate-match|rating-midpoint|midpoint button/, file);
  }
});
