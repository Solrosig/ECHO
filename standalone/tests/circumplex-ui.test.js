import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {EMOTIONS} from '../voice-controls.js';
import {QUADRANTS,targetName} from '../circumplex.js';

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

test('Listening reveals every frozen manifest target under its page name', () => {
  const manifest = JSON.parse(read('public/study/manifest.json'));
  const pageName = {Happy:'Happy', Upset:'Angry', Sad:'Sad', Calm:'Relaxed'};
  assert.ok(manifest.blocks.length > 0);
  for (const {block_id, target} of manifest.blocks) assert.equal(targetName(target), pageName[target.name], block_id);
  const listen = read('listen.js');
  assert.doesNotMatch(listen, /\$\{t\.target\.name\}/);
  assert.equal(listen.match(/\$\{targetName\(t\.target\)\}/g).length, 2);
});

test('every page uses the quadrant names, and Q numbers appear only inside the circle', () => {
  const calibration = read('public/calibration/index.html');
  assert.doesNotMatch(calibration, /\b(upset|calm)\b/i);
  for (const name of ['public/listener-instructions.html', 'public/ECHO_Application_Coverage_EN.csv']) assert.doesNotMatch(read(name), /\b(Upset|Calm)\b/, name);
  const studio = read('studio.html').replace(/<b><small>Q[1-4]<\/small> [A-Za-z]+<\/b>/g, '');
  const pages = ['app.js', 'listen.js', 'public/listener-instructions.html', 'public/calibration/index.html', 'public/ECHO_Application_Coverage_EN.csv'];
  for (const [name, text] of [['studio.html', studio], ...pages.map(page => [page, read(page)])]) {
    assert.doesNotMatch(text, /Q[1-4]\W{0,12}(Happy|Angry|Sad|Relaxed)/, name);
  }
});

test('the selected target shows only its bold name, and the quadrants are separated along the axes', () => {
  const studio = read('studio.html');
  assert.match(studio, /<strong id="target-name">Happy<\/strong><p>/);
  for (const name of ['studio.html', 'app.js', 'listen.js']) {
    assert.doesNotMatch(read(name), /target-coordinates|Valence \$\{|Valence [+−-]\d/, name);
  }
  const css = read('style.css');
  assert.match(css, /\.circumplex-disc\{[^}]*display:grid;[^}]*gap:6px/);
  assert.match(css, /\.target-note strong\{[^}]*font-weight:700/);
});

test('the retired calibration gallery is not linked and offers no recordings', () => {
  assert.doesNotMatch(read('studio.html'), /href="\/calibration\//);
  const calibration = read('public/calibration/index.html');
  assert.doesNotMatch(calibration, /<audio|examples\.js/);
  assert.match(calibration, /not part of the current study/);
});
