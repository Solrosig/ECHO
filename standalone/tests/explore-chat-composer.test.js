import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';

const read = path => readFileSync(new URL('../'+path, import.meta.url), 'utf8');

test('the Explore conversation window is 10% lower (author, 2026-09-15)', () => {
  assert.match(read('style.css'), /\.chat-messages\{[^}]*min-height:270px;max-height:558px;/);
});

test('a sent Explore message leaves the composer at once and comes back only if the exchange fails or is cancelled', () => {
  const app = read('app.js');
  const run = app.slice(app.indexOf('async function runChat(){'), app.indexOf('function cancel(){'));
  const shown = run.indexOf("$('chat-messages').append(userBubble,pending);");
  const cleared = run.indexOf("$('chat-message').value='';");
  assert.ok(shown >= 0 && cleared > shown && cleared - shown < 80, `shown ${shown}, cleared ${cleared}`);
  assert.equal(run.split("$('chat-message').value='';").length - 1, 1);
  assert.equal(run.split("if(!$('chat-message').value)$('chat-message').value=input;").length - 1, 2);
});
