import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync, readdirSync} from 'node:fs';

const read = path => readFileSync(new URL('../'+path, import.meta.url), 'utf8');
const NAME = 'ECHO - <strong>E</strong>motionally <strong>C</strong>o<strong>H</strong>erent c<strong>O</strong>nversational system - Open academic prototype';

test('every page footer names ECHO with the bold acronym letters and "Open academic prototype"', () => {
  const pages = readdirSync(new URL('../', import.meta.url)).filter(name => name.endsWith('.html'))
    .concat(['public/listener-instructions.html', 'public/calibration/index.html']);
  const withFooter = pages.filter(page => read(page).includes('<footer'));
  assert.deepEqual(withFooter.sort(), ['index.html', 'studio.html']);
  for (const page of withFooter) {
    const footer = read(page).match(/<footer>[\s\S]*?<\/footer>/)[0];
    assert.ok(footer.includes(`<span class="echo-acronym" aria-label="ECHO - Emotionally Coherent Conversational system - Open academic prototype">${NAME}</span>`), page);
    assert.doesNotMatch(footer, /ECHO · Open academic prototype/, page);
  }
  assert.match(read('style.css'), /\.echo-acronym strong\{[^}]*font-weight:700/);
});
