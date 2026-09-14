import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';

const read = path => readFileSync(new URL('../'+path, import.meta.url), 'utf8');

test('Test Mode puts each new recording at the top of the listening desk', () => {
  const app = read('app.js');
  assert.match(app, /\$\('results'\)\.prepend\(el\)/);
  assert.doesNotMatch(app, /\$\('results'\)\.append\(/);
  // At the 12-card cap the oldest card, now the last one, leaves together with the oldest record.
  assert.match(app, /records\.shift\(\);URL\.revokeObjectURL\(old\.url\);\$\('results'\)\.lastElementChild\.remove\(\)/);
});

test('the compare buttons sit below the recordings, at the end of the listening desk (author, 2026-09-14)', () => {
  const html = read('studio.html');
  const heading = html.indexOf('class="results-heading"');
  const results = html.indexOf('id="results"');
  const compare = html.indexOf('id="compare-actions"');
  const explore = html.indexOf('id="explore-panel"');
  assert.ok(heading >= 0 && heading < results && results < compare && compare < explore, `heading ${heading}, results ${results}, compare ${compare}, explore ${explore}`);
});
