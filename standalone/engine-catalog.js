// User-approved scope. Historical engines may remain in previous database rows.
export const LISTENING_ENGINES=['pyttsx3','sapi5xml','espeak','kokoro','chatterbox','zipvoice','styletts2','cosyvoice2','parlertts'];
export const TEST_ENGINES=['kokoro','chatterbox','styletts2','cosyvoice2','parlertts'];
// Provisional choice from archived evidence and the new fixed-text acoustic contrasts, not a human-validated ranking.
// CosyVoice 2 joined on 2026-09-27 as a trial voice, after the study's data collection closed.
export const EXPLORE_ENGINES=['chatterbox','parlertts','kokoro','cosyvoice2'];
// Explore-only labels. voice-controls.js is pinned by PROTOCOL_FREEZE_V2, so a name that differs from ENGINES[e].name lives here.
export const EXPLORE_NAMES={cosyvoice2:'CosyVoice 2 (Test)'};
export const ENGINE_NAMES={pyttsx3:'pyttsx3',sapi5xml:'SAPI5 XML',espeak:'eSpeak NG',kokoro:'Kokoro',chatterbox:'Chatterbox',zipvoice:'ZipVoice',styletts2:'StyleTTS2',cosyvoice2:'CosyVoice2',parlertts:'Parler-TTS'};
