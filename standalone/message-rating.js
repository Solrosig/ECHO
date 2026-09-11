import {validateRating,RATING_SCALE} from './study-session.js';
export const MESSAGE_RATING_VERSION='echo-message-rating-v1';
export function validateMessageRating(r){
 validateRating(r);
 if(r.rating_scale!==RATING_SCALE||r.version!==MESSAGE_RATING_VERSION)throw new Error('Reload the current message rating form.');
 if(!['valence','arousal'].every(k=>Math.abs(r[k]*100-Math.round(r[k]*100))<1e-8))throw new Error('Use the displayed rating steps.');
 if(r.completed_audio!==true||!Number.isInteger(r.play_count)||r.play_count<1||r.play_count>10000)throw new Error('Listen to the whole message at normal speed before rating it.');
 if(!Number.isFinite(r.elapsed_s)||r.elapsed_s<0||r.elapsed_s>86400||typeof r.created_utc!=='string'||r.created_utc.length>30||!Number.isFinite(Date.parse(r.created_utc)))throw new Error('Invalid rating metadata.');
 return r;
}
export const interactivePending=s=>(s.attempts||[]).some(a=>!(s.saved_attempt_orders||[]).includes(a.attempt_id))||s.turns.length>s.saved_count||Object.keys(s.ratings||{}).length>(s.saved_rating_count||0)||(s.audio_orders||[]).some(n=>!(s.saved_audio_orders||[]).includes(n));
