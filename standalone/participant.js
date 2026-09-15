import {TEST_ENGINES,EXPLORE_ENGINES} from './engine-catalog.js';
import {CONTROL_VERSION} from './voice-controls.js';
export const PROFILE_KEY='echo-nickname-v1';
export function validateNickname(value){
 const nickname=typeof value==='string'?value.trim().normalize('NFC'):'';
 if(!/^[\p{L}\p{N}][\p{L}\p{N}_ .-]{1,31}$/u.test(nickname))throw new Error('Enter a nickname of 2–32 characters using letters, numbers, spaces, dots, hyphens or underscores.');
 return nickname;
}
export function readNickname(){try{return validateNickname(localStorage.getItem(PROFILE_KEY));}catch{return '';}}
export function rememberNickname(value){const name=validateNickname(value);try{localStorage.setItem(PROFILE_KEY,name);}catch{}return name;}
export const NICKNAME_TAKEN='This nickname already exists. Change the nickname.';
// Gender is asked beside the nickname in every entry form and is required for a new session (author, 2026-09-15).
// Stored codes: female, male, na (shown as N/A). The choice is remembered in this browser like the nickname.
export const GENDER_KEY='echo-gender-v1';
export const GENDERS=Object.freeze({female:'Female',male:'Male',na:'N/A'});
export function validateGender(value){if(typeof value!=='string'||!Object.hasOwn(GENDERS,value))throw new Error('Choose your gender: Female, Male or N/A.');return value;}
export function readGender(){try{return validateGender(localStorage.getItem(GENDER_KEY));}catch{return '';}}
export function rememberGender(value){const gender=validateGender(value);try{localStorage.setItem(GENDER_KEY,gender);}catch{}return gender;}
// Ticks the remembered choice in a form's gender field; nothing is ticked when no valid choice is remembered.
export function fillGender(form,value=readGender()){for(const input of form.querySelectorAll('input[name=gender]'))input.checked=input.value===value;}
// Asks the server whether another browser already uses this nickname. When the check cannot run, the page continues and
// the server still refuses a duplicate when the new session is saved.
export async function nicknameAvailable(nickname,listener,fetcher=globalThis.fetch){
 try{const response=await fetcher.call(globalThis,'/api/nicknames/check',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({nickname,listener_id:listener})});
  if(!response.ok)return true;return (await response.json()).available!==false;}catch{return true;}
}
export const MAX_EXCHANGES=10;
export function validateConversationTurn(session,turn){
 if(!(session.mode==='explore'?EXPLORE_ENGINES:TEST_ENGINES).includes(turn.engine))throw new Error('Choose a TTS engine available in this mode.');
 if(session.mode==='explore'&&session.engine!==turn.engine)throw new Error('This conversation uses one fixed TTS engine. Start a new conversation to change it.');
 if(!Number.isInteger(turn.order)||turn.order<1||turn.order>(session.mode==='explore'?MAX_EXCHANGES:12))throw new Error('This session has reached its message limit. Start a new session.');
 if(!['happy','upset','sad','calm'].includes(turn.emotion))throw new Error('Choose an emotion.');
 for(const k of ['input_text','output_text'])if(typeof turn[k]!=='string'||!turn[k].trim()||turn[k].length>800)throw new Error('Messages must contain 1–800 characters.');
 if(session.mode==='line'&&turn.input_text!==turn.output_text)throw new Error('Test mode must use the exact input text.');
 if(!/^[a-f0-9]{64}$/.test(turn.audio_sha256||'')||!Number.isFinite(turn.duration_s)||turn.duration_s<=0||turn.duration_s>600)throw new Error('Invalid generated audio details.');
 if(!Number.isFinite(turn.elapsed_s)||turn.elapsed_s<0||turn.elapsed_s>3600||!Number.isFinite(Date.parse(turn.created_utc)))throw new Error('Invalid generation details.');
 if(!turn.controls||turn.controls.control_version!==CONTROL_VERSION||turn.controls.engine!==turn.engine||turn.controls.emotion!==turn.emotion||turn.controls.intensity!==1)throw new Error('Invalid voice settings.');
 if(turn.audio_metrics!==undefined){const m=turn.audio_metrics;if(!m||typeof m!=='object'||Array.isArray(m)||JSON.stringify(m).length>1200)throw new Error('Invalid acoustic metadata.');for(const k of ['pitch_shift_semitones','active_rms_dbfs','headroom_attenuation_db','peak','clipped_samples'])if(m[k]!==undefined&&!Number.isFinite(m[k]))throw new Error('Invalid acoustic metric.');}
 return turn;
}
