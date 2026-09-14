import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';

const read = path => readFileSync(new URL('../'+path, import.meta.url), 'utf8');
const LETTERS = '<strong>E</strong>motionally <strong>C</strong>o<strong>H</strong>erent c<strong>O</strong>nversational system';

test('the header brand spells out ECHO with the bold letters on every page that shows it', () => {
  for (const page of ['index.html', 'studio.html', 'listen.html', 'research.html']) {
    assert.match(read(page), new RegExp(`<a class="brand" href="[^"]+">ECHO<span class="brand-expansion">${LETTERS.replace(/\//g, '\\/')}</span>`), page);
  }
  assert.match(read('style.css'), /\.brand \.brand-expansion\{[^}]*font:inherit;font-weight:400/);
});

test('the Listening completion panel thanks the listener and says the responses are saved once received', () => {
  assert.ok(read('listen.html').includes('<h2>Thank you for completing the listening test.</h2>'));
  assert.match(read('listen.js'), /'Your responses are saved\. All responses have been received/);
  assert.match(read('public/listener-instructions.html'), /“Thank you for completing the listening test\.”/);
});
