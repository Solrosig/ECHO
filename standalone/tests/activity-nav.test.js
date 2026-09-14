import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';

const read = path => readFileSync(new URL('../'+path, import.meta.url), 'utf8');
const LINKS = [['/', 'Home'], ['/studio?mode=listening', 'Listening Test'], ['/studio?mode=line', 'Test Mode'], ['/studio?mode=explore', 'Explore Mode']];

test('every page except the homepage starts with links to Home, Listening Test, Test Mode and Explore Mode', () => {
  const pages = ['studio.html', 'listen.html', 'research.html', 'public/README.html', 'public/listener-instructions.html', 'public/calibration/index.html'];
  for (const page of pages) {
    const nav = read(page).match(/<nav class="activity-nav" aria-label="Activities">[\s\S]*?<\/nav>/)?.[0];
    assert.ok(nav, page);
    for (const [href, label] of LINKS) assert.match(nav, new RegExp(`<a href="${href.replace(/[?]/g, '\\?')}"[^>]*>${label}</a>`), `${page}: ${label}`);
  }
  // The homepage already offers the three activities as cards, so its header has no activity links (author, 2026-09-14).
  assert.doesNotMatch(read('index.html'), /class="activity-nav"/);
  assert.match(read('listen.html'), /<a href="\/studio\?mode=listening" class="selected" aria-current="page">Listening Test<\/a>/);
});

test('the studio marks the current activity instead of hiding the links', () => {
  assert.doesNotMatch(read('studio.html'), /hidden>Listening test<\/a>/);
  const app = read('app.js');
  assert.doesNotMatch(app, /listeningLink\.hidden=true/);
  assert.match(app, /querySelectorAll\('\.topbar \[data-nav-mode\]'\)/);
  assert.match(read('style.css'), /\.topbar:has\(\.activity-nav\)\{/);
});
