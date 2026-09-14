import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';

const read = path => readFileSync(new URL('../'+path, import.meta.url), 'utf8');

test('the Project guide link is hidden on every page that shows it; the guide itself stays reachable by its address', () => {
  assert.ok(read('index.html').includes('<a class="home-about-link" href="/README.html" hidden>Project guide</a>'));
  assert.ok(read('studio.html').includes('<a href="/README.html" hidden>Project guide</a>'));
  for (const page of ['index.html', 'studio.html', 'listen.html', 'research.html', 'public/listener-instructions.html', 'public/calibration/index.html']) {
    assert.doesNotMatch(read(page), /<a [^>]*href="\/README\.html"(?![^>]*hidden)[^>]*>/, page);
  }
});
