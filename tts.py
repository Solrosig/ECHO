"""TTS adapter — PROTECTED SEAM #2 (speech side).

`synthesize(text, voice_params) -> Path` writes a WAV. Engines share one interface:
  - KokoroAdapter    : high-quality open-source neural TTS (rate + volume)
  - Sapi5XmlAdapter  : Windows SAPI5 via prosody XML — renders rate + volume + PITCH
  - Pyttsx3Adapter   : offline OS voice (rate + volume; no pitch) — safe fallback
  - MockTTSAdapter   : dependency-free, for tests / offline integration runs

Voice dials arrive pre-computed on `voice_params` (rate, volume, pitch).
"""

from __future__ import annotations

import wave
from abc import ABC, abstractmethod
from pathlib import Path

from strategies import VoiceParams


class TTSAdapter(ABC):
    engine_id: str = "abstract"

    @abstractmethod
    def synthesize(self, text: str, voice_params: VoiceParams, out_path: Path) -> Path: ...


class MockTTSAdapter(TTSAdapter):
    """Writes a valid silent WAV whose length shrinks as rate rises (no deps)."""

    engine_id = "mock"
    _SR = 24000

    def synthesize(self, text: str, voice_params: VoiceParams, out_path: Path) -> Path:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        base = max(len(text), 1) / 15.0  # ~seconds of "speech"
        seconds = max(0.2, base / max(voice_params.rate, 0.1))
        n = int(self._SR * seconds)
        with wave.open(str(out_path), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(self._SR)
            w.writeframes(b"\x00\x00" * n)
        return out_path


class Pyttsx3Adapter(TTSAdapter):
    """Offline OS voice (Windows SAPI5). Renders rate + volume (no pitch)."""

    engine_id = "pyttsx3"
    _BASE_WPM = 175

    def synthesize(self, text: str, voice_params: VoiceParams, out_path: Path) -> Path:
        import pyttsx3

        out_path.parent.mkdir(parents=True, exist_ok=True)
        engine = pyttsx3.init()
        engine.setProperty("rate", int(self._BASE_WPM * voice_params.rate))
        engine.setProperty("volume", max(0.0, min(1.0, voice_params.volume)))
        engine.save_to_file(text, str(out_path))
        engine.runAndWait()
        engine.stop()
        return out_path


# --- SAPI dial calibration -------------------------------------------------
# SAPI's tags run -10..+10, but those extremes are NOT linear and NOT modest:
#   absspeed=+10 is ~3x speaking rate; absmiddle=+10 is a chipmunk-level pitch jump.
# The intended dials are gentle (rate 0.7-1.3, pitch 0.8-1.2). The earlier code
# stretched that gentle band across SAPI's whole extreme range, so a "1.3x" intent
# rendered as ~2-3x actual speed (unlistenable). These helpers instead map each
# dial onto the SMALL part of SAPI's scale that reproduces the intended factor.

def _sapi_rate(rate_factor: float) -> int:
    """Rate factor -> SAPI absspeed. Gain 17 gives a CLEAR fast/slow contrast between
    quadrants (1.18 -> +3 ~1.4x, 0.82 -> -3 ~0.7x); the +-5 cap keeps even the extremes
    listenable (never SAPI's +10 ~= 3x, which was unlistenable)."""
    return max(-5, min(5, round((rate_factor - 1.0) * 17.0)))


def _sapi_pitch(pitch_factor: float) -> int:
    """Pitch factor -> SAPI absmiddle. This is the valence channel: gain 20 turns the
    +-0.2 pitch range into an audible +-4 shift (Q1 high vs Q2 low), clamped +-5 so it
    can never chipmunk."""
    return max(-5, min(5, round((pitch_factor - 1.0) * 20.0)))


def _sapi_volume(volume: float) -> int:
    """Loudness dial (0.6..1.0) -> SAPI volume 50..95: a WIDE dynamic range so 'loud'
    quadrants (~86) are clearly louder than 'soft' ones (~59); floor 50 stays audible,
    ceiling 95 avoids blasting."""
    v = max(0.6, min(1.0, volume))
    return max(0, min(100, round(50.0 + (v - 0.6) / 0.4 * 45.0)))


def _xml_escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


class Sapi5XmlAdapter(TTSAdapter):
    """Windows SAPI5 driven with prosody XML markup, so PITCH is rendered too.

    Uses pywin32 (win32com). Maps rate/volume/pitch onto SAPI's <rate>, <volume>,
    and <pitch> tags. This is the engine that finally carries valence (via pitch)
    into the voice.
    """

    engine_id = "sapi5xml"

    def synthesize(self, text: str, voice_params: VoiceParams, out_path: Path) -> Path:
        import win32com.client  # Windows only (pywin32)

        out_path.parent.mkdir(parents=True, exist_ok=True)
        rate_i = _sapi_rate(voice_params.rate)
        pitch_i = _sapi_pitch(voice_params.pitch)
        vol_pct = _sapi_volume(voice_params.volume)

        xml = (
            f'<volume level="{vol_pct}">'
            f'<rate absspeed="{rate_i}">'
            f'<pitch absmiddle="{pitch_i}">{_xml_escape(text)}</pitch>'
            f"</rate></volume>"
        )
        voice = win32com.client.Dispatch("SAPI.SpVoice")
        stream = win32com.client.Dispatch("SAPI.SpFileStream")
        stream.Open(str(out_path), 3, False)   # 3 = SSFMCreateForWrite
        voice.AudioOutputStream = stream
        try:
            voice.Speak(xml, 8)                # 8 = SVSFIsXML
        finally:
            stream.Close()
        return out_path


class KokoroAdapter(TTSAdapter):
    """High-quality open-source neural TTS via kokoro-onnx. Renders rate + volume."""

    engine_id = "kokoro"

    def __init__(self, model_path: str, voices_path: str, lang: str = "en-us") -> None:
        from kokoro_onnx import Kokoro

        self._kokoro = Kokoro(model_path, voices_path)
        self._lang = lang

    def synthesize(self, text: str, voice_params: VoiceParams, out_path: Path) -> Path:
        import soundfile as sf

        out_path.parent.mkdir(parents=True, exist_ok=True)
        samples, sample_rate = self._kokoro.create(
            text,
            voice=voice_params.voice_id,
            speed=voice_params.rate,
            lang=self._lang,
        )
        samples = samples * max(0.0, min(1.0, voice_params.volume))  # apply loudness
        sf.write(str(out_path), samples, sample_rate)
        return out_path


def make_tts(engine: str, *, kokoro_model: str, kokoro_voices: str) -> TTSAdapter:
    """Select an engine.

    'mock' | 'pyttsx3' | 'sapi' (=sapi5xml, renders pitch) | 'kokoro' | 'auto'.
    'auto' prefers Kokoro if its model files exist, else pyttsx3 (the safe default).
    """
    choice = engine.lower()
    if choice == "mock":
        return MockTTSAdapter()
    if choice == "pyttsx3":
        return Pyttsx3Adapter()
    if choice in ("sapi", "sapi5", "sapi5xml"):
        return Sapi5XmlAdapter()
    if choice == "kokoro":
        return KokoroAdapter(kokoro_model, kokoro_voices)
    # auto
    if Path(kokoro_model).exists() and Path(kokoro_voices).exists():
        try:
            return KokoroAdapter(kokoro_model, kokoro_voices)
        except Exception:
            pass
    return Pyttsx3Adapter()
