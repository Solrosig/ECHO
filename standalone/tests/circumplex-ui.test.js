import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {EMOTIONS} from '../voice-controls.js';
import {QUADRANTS} from '../circumplex.js';

const read = path => readFileSync(new URL('../'+path, import.meta.url), 'utf8');

test('each page name sits in the circumplex quadrant of its frozen preset coordinates', () => {
  assert.deepEqual(Object.keys(QUADRANTS).sort(), Object.keys(EMOTIONS).sort());
  const signs = {Q1:[1,1], Q2:[-1,1], Q3:[-1,-1], Q4:[1,-1]};
  for (const [id, q] of Object.entries(QUADRANTS)) {
    assert.deepEqual([Math.sign(EMOTIONS[id].v), Math.sign(EMOTIONS[id].a)], signs[q.quadrant], id);
    assert.equal(q.description.split(' · ').length, 2, id);
  }
  assert.deepEqual(Object.values(QUADRANTS).map(q => `${q.quadrant} ${q.name}`).sort(), ['Q1 Happy','Q2 Angry','Q3 Sad','Q4 Relaxed']);
});

test('the studio shows exactly four quadrants in circumplex order, with the axis synonyms', () => {
  const html = read('studio.html');
  const quadrants = [...html.matchAll(/<label class="quadrant (q[1-4])[^"]*" data-emotion="([a-z]+)">[\s\S]*?<b><small>(Q[1-4])<\/small> ([A-Za-z]+)<\/b><span>([^<]+)<\/span><\/label>/g)];
  assert.deepEqual(quadrants.map(m => m[2]), ['upset','happy','sad','calm']);
  for (const [, cls, id, quadrant, name, description] of quadrants) {
    assert.equal(cls, quadrant.toLowerCase());
    assert.deepEqual({quadrant, name, description}, QUADRANTS[id]);
  }
  assert.match(html, /<dt>Valence<\/dt><dd>Positive vs\. Negative<\/dd>/);
  assert.match(html, /<dt>Arousal<\/dt><dd>Intense vs\. Calm<\/dd>/);
  assert.doesNotMatch(html, /emotion-grid|class="emotion[ "]/);
});

test('the page names targets through QUADRANTS, not the frozen preset names', () => {
  assert.doesNotMatch(read('app.js'), /EMOTIONS\[[^\]]+\]\.name/);
});
