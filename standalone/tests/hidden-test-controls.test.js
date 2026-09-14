import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';

const read = path => readFileSync(new URL('../'+path, import.meta.url), 'utf8');

test('Test Mode hides the individual controls and the gain and pitch readouts (author, 2026-09-14)', () => {
  const studio = read('studio.html');
  assert.ok(studio.includes('<details class="advanced" hidden><summary>Explore individual controls</summary>'));
  assert.ok(studio.includes('<div hidden><dt>Output gain</dt><dd id="gain-readout"></dd></div>'));
  assert.ok(studio.includes('<div hidden><dt>Pitch control</dt><dd id="pitch-readout"></dd></div>'));
  // The controls stay in the page, hidden, so the app keeps its default Emotion preset condition.
  assert.match(studio, /<select id="condition"><option value="preset">Emotion preset<\/option>/);
  assert.ok(studio.includes('<div><dt>Speaking rate</dt><dd id="rate-readout"></dd></div>'));
});

test('the listener guide no longer sends people to the hidden controls', () => {
  const guide = read('public/listener-instructions.html');
  for (const phrase of ['Explore individual controls', 'Control condition', 'Output gain', 'Pitch control']) assert.ok(!guide.includes(phrase), phrase);
});
