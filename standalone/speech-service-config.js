// The independent server proxies to its own Python speech service.
export const SPEECH_SERVICE=new URL('/api/tts',globalThis.location?.origin||'http://127.0.0.1:8787').href;
