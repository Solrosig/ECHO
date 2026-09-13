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

test('the compare buttons sit between the desk heading and the newest recording', () => {
  const html = read('studio.html');
  const heading = html.indexOf('class="results-heading"');
  const compare = html.indexOf('id="compare-actions"');
  const results = html.indexOf('id="results"');
  assert.ok(heading >= 0 && heading < compare && compare < results, `heading ${heading}, compare ${compare}, results ${results}`);
});
