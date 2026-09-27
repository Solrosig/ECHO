// User-approved scope. Historical engines may remain in previous database rows.
export const LISTENING_ENGINES=['pyttsx3','sapi5xml','espeak','kokoro','chatterbox','zipvoice','styletts2','cosyvoice2','parlertts'];
export const TEST_ENGINES=['kokoro','chatterbox','styletts2','cosyvoice2','parlertts'];
// The report's shortlist (selection rule on the frozen-45 scorecard): CosyVoice 2, Chatterbox, Kokoro. Set on 2026-09-27,
// after the study's data collection closed; earlier Explore sessions may name Parler-TTS.
export const EXPLORE_ENGINES=['chatterbox','kokoro','cosyvoice2'];
// Explore-only labels. voice-controls.js is pinned by PROTOCOL_FREEZE_V2, so a name that differs from ENGINES[e].name lives here.
export const EXPLORE_NAMES={cosyvoice2:'CosyVoice 2'};
export const ENGINE_NAMES={pyttsx3:'pyttsx3',sapi5xml:'SAPI5 XML',espeak:'eSpeak NG',kokoro:'Kokoro',chatterbox:'Chatterbox',zipvoice:'ZipVoice',styletts2:'StyleTTS2',cosyvoice2:'CosyVoice2',parlertts:'Parler-TTS'};
