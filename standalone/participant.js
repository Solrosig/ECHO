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
