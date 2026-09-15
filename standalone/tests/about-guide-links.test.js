import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';

const read = path => readFileSync(new URL('../'+path, import.meta.url), 'utf8');
const LINKS = '<nav class="page-links" aria-label="Guides"><a href="/README.html">About Project</a><a href="/listener-instructions.html">Listener Guide</a></nav>';

test('every page header ends with the About project and Listener guide links (author, 2026-09-14)', () => {
  for (const page of ['index.html', 'studio.html', 'listen.html', 'research.html']) {
    const header = read(page).match(/<header class="topbar">[\s\S]*?<\/header>/)?.[0];
    assert.ok(header, page);
    // Pages with activity links keep them beside the guide links, at the right of the header (author, 2026-09-15).
    assert.ok(header.endsWith(LINKS + (page === 'index.html' ? '</header>' : '</div></header>')), page);
    if (page !== 'index.html') assert.ok(header.includes('<div class="header-links"><nav class="activity-nav"'), page);
  }
  assert.match(read('style.css'), /\.topbar \.page-links\{margin-left:auto;/);
});

test('"Project guide" and "Listener instructions" are renamed everywhere a visitor sees them', () => {
  for (const page of ['index.html', 'studio.html', 'listen.html', 'research.html', 'public/listener-instructions.html', 'public/calibration/index.html']) {
    const html = read(page);
    assert.doesNotMatch(html, /Project guide/i, page);
    assert.doesNotMatch(html, /Listener instructions/i, page);
    assert.doesNotMatch(html, /<a [^>]*hidden[^>]*>/, page);
  }
  assert.match(read('public/listener-instructions.html'), /<title>ECHO Listener Guide<\/title>[\s\S]*<h1>ECHO Listener Guide<\/h1>/);
  assert.match(read('listen.html'), /Read the step-by-step listener guide<\/a>/);
});
