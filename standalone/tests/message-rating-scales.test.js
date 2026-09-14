import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {validateMessageRating,MESSAGE_RATING_VERSION,MESSAGE_RATING_SCALE} from '../message-rating.js';
import {RATING_SCALE} from '../study-session.js';

const read = path => readFileSync(new URL('../'+path, import.meta.url), 'utf8');
const meta = {completed_audio:true, play_count:1, elapsed_s:3, created_utc:'2026-09-14T08:00:00Z'};

test('Test Mode and Explore rate valence and arousal in nine steps and naturalness in half steps', () => {
  const rating = {valence:-.75, arousal:.25, naturalness:3.5, target_match:4.5, rating_scale:MESSAGE_RATING_SCALE, version:MESSAGE_RATING_VERSION, ...meta};
  assert.equal(validateMessageRating(rating), rating);
  for (const change of [{valence:.37}, {arousal:-.6}, {naturalness:3.25}, {naturalness:0.5}, {target_match:5.5}, {rating_scale:RATING_SCALE}]) {
    assert.throws(() => validateMessageRating({...rating, ...change}), undefined, JSON.stringify(change));
  }
});

test('a rating queued by an earlier page keeps its own scale', () => {
  assert.ok(validateMessageRating({valence:.37, arousal:-.42, naturalness:4, target_match:3.5, rating_scale:RATING_SCALE, version:'echo-message-rating-v1', ...meta}));
  assert.throws(() => validateMessageRating({valence:.37, arousal:-.42, naturalness:3.5, target_match:3.5, rating_scale:RATING_SCALE, version:'echo-message-rating-v1', ...meta}));
});

test('the message rating form and instructions show the new steps; Listening keeps its frozen scale', () => {
  const ui = read('message-rating-ui.js');
  for (const text of ["'How positive or negative does the voice sound?',-100,100,25,", "'How much energy does the voice transmit?',-100,100,25,", "'How natural does the voice sound?',1,5,.5,", 'const ticks=9;', 'rating_scale:MESSAGE_RATING_SCALE']) assert.ok(ui.includes(text), text);
  assert.doesNotMatch(ui, /convey/);
  const guide = read('public/listener-instructions.html');
  assert.ok(guide.includes('“How much energy does the voice transmit?”'));
  assert.doesNotMatch(guide, /convey\?/);
  assert.equal(RATING_SCALE, 'va-0.01_match-0.5_naturalness-1_v2');
});
