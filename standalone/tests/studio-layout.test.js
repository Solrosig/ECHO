import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';

const read = path => readFileSync(new URL('../'+path, import.meta.url), 'utf8');
const studio = read('studio.html');

test('New conversation sits under the voice lock note, inside the engine block', () => {
  const engine = studio.match(/<div class="chat-engine">[\s\S]*?<\/div>\s*<div id="chat-messages"/)[0];
  assert.match(engine, /id="engine-lock-note"[^>]*>[^<]*<\/p><div class="chat-actions"><button id="new-conversation"/);
  assert.equal(studio.match(/id="new-conversation"/g).length, 1);
});

test('the privacy text follows "Built with Llama" on every mode of the page, not the footer', () => {
  const text = 'Kokoro speech runs in your browser.';
  assert.equal(studio.split(text).length - 1, 1);
  assert.match(studio, /Llama 3\.2 Community License<\/a><\/p>\s*<\/section>\s*<p class="privacy-note">Kokoro speech runs in your browser\./);
  assert.doesNotMatch(studio.slice(studio.indexOf('<footer>')), /Kokoro speech runs/);
  assert.match(read('style.css'), /\.privacy-note\{[^}]*font-size:12px/);
});
