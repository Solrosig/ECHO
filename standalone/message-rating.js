import {validateRating,RATING_SCALE} from './study-session.js';
// v2 (2026-09-14): Test Mode and Explore rate valence and arousal in nine steps (-1 to 1 by 0.25) and naturalness in half
// steps, like the match. Listening keeps its frozen scale. A rating an earlier page queued (v1) is still accepted on its own scale.
export const MESSAGE_RATING_VERSION='echo-message-rating-v2';
export const MESSAGE_RATING_SCALE='va-0.25_match-0.5_naturalness-0.5_v3';
const PREVIOUS_VERSION='echo-message-rating-v1';
const halfStep=v=>Number.isFinite(v)&&Number.isInteger(v*2)&&v>=1&&v<=5;
export function validateMessageRating(r){
 if(r.version===PREVIOUS_VERSION){
  validateRating(r);
  if(r.rating_scale!==RATING_SCALE)throw new Error('Reload the current message rating form.');
  if(!['valence','arousal'].every(k=>Math.abs(r[k]*100-Math.round(r[k]*100))<1e-8))throw new Error('Use the displayed rating steps.');
 }else{
  if(r.rating_scale!==MESSAGE_RATING_SCALE||r.version!==MESSAGE_RATING_VERSION)throw new Error('Reload the current message rating form.');
  if(!['valence','arousal'].every(k=>Number.isFinite(r[k])&&r[k]>=-1&&r[k]<=1&&Number.isInteger(r[k]*4)))throw new Error('Use the displayed rating steps.');
  if(!halfStep(r.naturalness))throw new Error('Choose a naturalness rating.');
  if(!halfStep(r.target_match))throw new Error('Choose a target-match rating.');
 }
 if(r.completed_audio!==true||!Number.isInteger(r.play_count)||r.play_count<1||r.play_count>10000)throw new Error('Listen to the whole message at normal speed before rating it.');
 if(!Number.isFinite(r.elapsed_s)||r.elapsed_s<0||r.elapsed_s>86400||typeof r.created_utc!=='string'||r.created_utc.length>30||!Number.isFinite(Date.parse(r.created_utc)))throw new Error('Invalid rating metadata.');
 return r;
}
export const interactivePending=s=>(s.attempts||[]).some(a=>!(s.saved_attempt_orders||[]).includes(a.attempt_id))||s.turns.length>s.saved_count||Object.keys(s.ratings||{}).length>(s.saved_rating_count||0)||(s.audio_orders||[]).some(n=>!(s.saved_audio_orders||[]).includes(n));
