import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';

const read = path => readFileSync(new URL('../'+path, import.meta.url), 'utf8');

test('the About project page carries the author\'s text and nothing from the old installation guide (author, 2026-09-14)', () => {
  const page = read('public/README.html');
  assert.match(page, /<title>About ECHO<\/title>/);
  assert.match(page, /<h1>About project<\/h1><h2>What ECHO is<\/h2><p>ECHO \(Emotionally CoHerent cOnversational system\) is an academic project/);
  assert.ok(page.includes('four quadrants of Russell&#x27;s circumplex model.'));
  assert.ok(page.includes('No commercial voice service is used.</p><h2>The research goal</h2>'));
  const questions = page.match(/<p>Your feedback helps answer:<\/p><ul>([\s\S]*?)<\/ul>/)?.[1].match(/<li>/g) ?? [];
  assert.equal(questions.length, 4);
  for (const old of ['ECHO standalone final', 'Start locally', 'Researcher password', 'Database and backup', 'thesis/ECHO_Thesis_EN.docx', 'Listener instructions']) {
    assert.ok(!page.includes(old), old);
  }
  assert.ok(page.includes('<a href="/listener-instructions.html">Listener guide</a> · <a href="/research">Researcher access</a>'));
});
