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
    renders: frozenset = frozenset()   # which dials this engine actually renders (rate/volume/pitch)
    natural: bool = False              # neural/natural voice (vs formant/concatenative)
    native_emotion: bool = False       # conditions on the EMOTION itself, not on prosody dials
    note: str = ""

    @abstractmethod
    def synthesize(self, text: str, voice_params: VoiceParams, out_path: Path) -> Path: ...


class MockTTSAdapter(TTSAdapter):
    """Writes a valid silent WAV whose length shrinks as rate rises (no deps)."""

    engine_id = "mock"
    renders = frozenset()                       # silent; renders no audible dial
    note = "silent WAV; tests only"
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
    renders = frozenset({"rate", "volume"})     # OS voice: no pitch control
    note = "OS voice (SAPI/espeak/nsss); no pitch; not cross-platform-consistent"
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
    renders = frozenset({"rate", "volume", "pitch"})   # full dial set (pitch via XML)
    note = "Windows-only; not OSS; rough voice quality"

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
    renders = frozenset({"rate", "volume"})     # neural: speed + loudness; no explicit pitch dial
    natural = True
    note = "neural, Apache-2.0, local (ONNX); high naturalness; no explicit pitch"

    def __init__(self, model_path: str, voices_path: str, lang: str = "en-us") -> None:
        self._model_path = model_path
        self._voices_path = voices_path
        self._lang = lang
        self._kokoro = None                        # lazy: model loaded on first synthesize

    def _engine(self):
        """Load the ONNX model on first use, with clear errors for the two failure modes."""
        if self._kokoro is None:
            try:
                from kokoro_onnx import Kokoro
            except Exception as exc:               # package not installed
                raise RuntimeError(
                    "kokoro-onnx not installed — `pip install kokoro-onnx` (optional neural engine)."
                ) from exc
            missing = [p for p in (self._model_path, self._voices_path) if not Path(p).exists()]
            if missing:
                raise RuntimeError(
                    f"Kokoro model files not found: {missing}. Download kokoro-v1.0.onnx + "
                    "voices-v1.0.bin (kokoro-onnx releases) and set ECHO_KOKORO_MODEL / ECHO_KOKORO_VOICES."
                )
            self._kokoro = Kokoro(self._model_path, self._voices_path)
        return self._kokoro

    def synthesize(self, text: str, voice_params: VoiceParams, out_path: Path) -> Path:
        engine = self._engine()                    # validate package + model first (clear errors)
        import soundfile as sf

        out_path.parent.mkdir(parents=True, exist_ok=True)
        samples, sample_rate = engine.create(
            text,
            voice=voice_params.voice_id,
            speed=voice_params.rate,
            lang=self._lang,
        )
        samples = samples * max(0.0, min(1.0, voice_params.volume))  # apply loudness
        sf.write(str(out_path), samples, sample_rate)
        return out_path


def arousal_to_exaggeration(arousal: float, lo: float = 0.30, hi: float = 0.85) -> float:
    """Arousal (-1..1) -> Chatterbox `exaggeration` (0..1, default 0.5): the engine's NATIVE
    expressiveness control. Low arousal -> subdued delivery, high arousal -> emphatic."""
    return round(lo + (max(-1.0, min(1.0, arousal)) + 1.0) / 2.0 * (hi - lo), 3)


def arousal_to_cfg_weight(arousal: float, lo: float = 0.30, hi: float = 0.60) -> float:
    """Arousal -> Chatterbox `cfg_weight` (default 0.5). Higher exaggeration speeds speech up,
    and LOWERING cfg_weight restores slower, more deliberate pacing — so high-arousal clips get
    a lower cfg to stay intelligible, low-arousal clips a higher one."""
    return round(hi - (max(-1.0, min(1.0, arousal)) + 1.0) / 2.0 * (hi - lo), 3)


class _NoWatermark:
    """No-op stand-in for Chatterbox's Perth watermarker (same call signature)."""

    def apply_watermark(self, wav, sample_rate=None, **kwargs):
        return wav


def _disable_perth_watermark() -> None:
    """Disable Chatterbox's inaudible audio watermarking — for TWO reasons.

    1. MEASUREMENT VALIDITY (the important one): the watermarker deliberately perturbs the
       output waveform, and ECHO *measures* that waveform (F0, jitter, shimmer, HNR, UTMOS).
       Watermarked audio is therefore not a clean sample of what the engine synthesised, so it
       is switched off for research use. Any published clip can be re-rendered with it enabled.
    2. ROBUSTNESS: `resemble-perth` only imports fully when its own optional dependencies are
       present; otherwise `perth.PerthImplicitWatermarker` is left as None and Chatterbox dies
       with `TypeError: 'NoneType' object is not callable` while loading the model.
    """
    try:
        import perth
    except Exception:
        return                                  # not installed at all -> Chatterbox handles it
    perth.PerthImplicitWatermarker = lambda *a, **k: _NoWatermark()


class ChatterboxAdapter(TTSAdapter):
    """Chatterbox (Resemble AI, MIT) — neural TTS with NATIVE emotion conditioning.

    This adapter is the experiment behind Phase X: the Phase-N result showed a neutral neural
    engine discards externally-applied prosody (flat F0, emotion collapsed), so emotion is
    injected here through the engine's OWN interfaces instead of ECHO's dials:
      * `exaggeration`  <- AROUSAL   (native expressiveness scalar)
      * `cfg_weight`    <- AROUSAL   (pacing compensation; see arousal_to_cfg_weight)
      * `audio_prompt`  <- QUADRANT  (a per-quadrant emotional reference clip -> style transfer;
                                      this is the channel intended to carry VALENCE, the axis
                                      that prosodic dials failed to convey)
    Loudness is still applied as a post-scale. Rate and pitch are NOT sent — deliberately, since
    the point is to test native conditioning rather than to re-impose external prosody.

    Optional reference clips: a directory (config `chatterbox_refs`) containing Q1.wav..Q4.wav.
    Without them the engine still runs (expressiveness only, no valence style transfer).
    """

    engine_id = "chatterbox"
    renders = frozenset({"volume"})          # loudness only, as a post-scale
    natural = True
    native_emotion = True
    note = "neural, MIT; native emotion (exaggeration<-arousal, reference style<-quadrant)"

    #: files ChatterboxTTS.from_local() expects in a model directory
    MODEL_FILES = ("ve.safetensors", "t3_cfg.safetensors", "s3gen.safetensors",
                   "tokenizer.json", "conds.pt")

    def __init__(self, refs_dir: str = "", device: str = "cpu", model_dir: str = "") -> None:
        self._refs_dir = refs_dir
        self._device = device
        self._model_dir = model_dir
        self._model = None                    # lazy: heavy model loaded on first synthesis

    def _engine(self):
        if self._model is None:
            try:
                from chatterbox.tts import ChatterboxTTS
            except Exception as exc:
                raise RuntimeError(
                    "chatterbox-tts not installed — `pip install chatterbox-tts` (optional "
                    "expressive engine; needs torch)."
                ) from exc
            _disable_perth_watermark()
            # Prefer a LOCAL model directory when provided: networks that intercept TLS block
            # the Hugging Face download entirely (WinError 10054), so the files can be fetched
            # once in a browser instead — the same workaround used for the SER model.
            local = Path(self._model_dir) if self._model_dir else None
            if local and local.is_dir():
                missing = [f for f in self.MODEL_FILES if not (local / f).exists()]
                if missing:
                    raise RuntimeError(
                        f"Chatterbox model dir '{local}' is missing: {missing}. Download the five "
                        "files from https://huggingface.co/ResembleAI/chatterbox/tree/main"
                    )
                self._model = ChatterboxTTS.from_local(str(local), device=self._device)
                self._model.watermarker = _NoWatermark()      # unwatermarked audio for analysis
                return self._model
            try:
                self._model = ChatterboxTTS.from_pretrained(device=self._device)
                self._model.watermarker = _NoWatermark()      # unwatermarked audio for analysis
            except Exception as exc:
                raise RuntimeError(
                    f"Could not load the Chatterbox model ({exc}).\n"
                    "If the Hugging Face download is blocked by your network, either retry (it is "
                    "often intermittent), or set HF_HUB_DISABLE_XET=1 and retry, or download these "
                    f"files once in a BROWSER from\n"
                    "  https://huggingface.co/ResembleAI/chatterbox/tree/main\n"
                    f"  {', '.join(self.MODEL_FILES)}\n"
                    "into a folder and pass it via ECHO_CHATTERBOX_MODEL (e.g. cb_model)."
                ) from exc
        return self._model

    def _reference_for(self, quadrant: str) -> "str | None":
        """Per-quadrant emotional reference clip, if one has been provided."""
        if not self._refs_dir or not quadrant:
            return None
        cand = Path(self._refs_dir) / f"{quadrant}.wav"
        return str(cand) if cand.exists() else None

    def synthesize(self, text: str, voice_params: VoiceParams, out_path: Path) -> Path:
        model = self._engine()
        import numpy as np
        import soundfile as sf

        out_path.parent.mkdir(parents=True, exist_ok=True)
        kwargs = {
            "exaggeration": arousal_to_exaggeration(voice_params.arousal),
            "cfg_weight": arousal_to_cfg_weight(voice_params.arousal),
        }
        ref = self._reference_for(voice_params.quadrant)
        if ref:
            kwargs["audio_prompt_path"] = ref          # style/valence via reference audio
        wav = model.generate(text, **kwargs)

        samples = np.asarray(wav.squeeze().detach().cpu().numpy() if hasattr(wav, "detach")
                             else wav).astype("float32")
        samples = samples * max(0.0, min(1.0, voice_params.volume))       # loudness post-scale
        sf.write(str(out_path), samples, int(getattr(model, "sr", 24000)))
        return out_path


def _espeak_speed(rate: float) -> int:
    """Rate factor -> eSpeak words-per-minute (base 175), clamped to eSpeak's range."""
    return max(80, min(450, round(175 * rate)))


def _espeak_pitch(pitch: float) -> int:
    """Pitch factor (~0.8..1.2) -> eSpeak pitch 0..99 (50 = default). eSpeak gives REAL
    pitch control, so +-0.2 maps to a clear +-20 -- unlike SAPI's compressed absmiddle."""
    return max(0, min(99, round(50 + (pitch - 1.0) * 100)))


def _espeak_amp(volume: float) -> int:
    """Loudness 0..1 -> eSpeak amplitude 0..200 (100 = default)."""
    return max(0, min(200, round(max(0.0, min(1.0, volume)) * 150)))


def _find_espeak() -> "str | None":
    """Locate the eSpeak NG binary robustly: the ECHO_ESPEAK_BIN override first, then PATH,
    then the standard Windows install dirs (the MSI does not always add itself to PATH)."""
    import os
    import shutil

    env = os.getenv("ECHO_ESPEAK_BIN")
    if env and Path(env).exists():
        return env
    for name in ("espeak-ng", "espeak"):
        found = shutil.which(name)
        if found:
            return found
    for cand in (r"C:\Program Files\eSpeak NG\espeak-ng.exe",
                 r"C:\Program Files (x86)\eSpeak NG\espeak-ng.exe"):
        if Path(cand).exists():
            return cand
    return None


class EspeakNgAdapter(TTSAdapter):
    """Open-source, cross-platform formant synthesizer (eSpeak NG) via its CLI.

    Full explicit control of rate, volume, AND pitch -- a controllable open-source
    baseline that supersedes SAPI's role without the Windows lock-in. Robotic (low
    naturalness): a controllability baseline, not a naturalness contender.
    Needs the `espeak-ng` binary on PATH (apt / brew / choco / installer).
    """

    engine_id = "espeak"
    renders = frozenset({"rate", "volume", "pitch"})
    note = "open-source, cross-platform (GPLv3); full parametric control; robotic"

    def synthesize(self, text: str, voice_params: VoiceParams, out_path: Path) -> Path:
        import subprocess

        out_path.parent.mkdir(parents=True, exist_ok=True)
        exe = _find_espeak()
        if not exe:
            raise RuntimeError(
                "espeak-ng not found. Install it (Windows: choco install espeak-ng; "
                "Linux: apt install espeak-ng; macOS: brew install espeak-ng), then REOPEN the "
                "terminal so PATH updates — or set ECHO_ESPEAK_BIN to the full path of espeak-ng.exe."
            )
        subprocess.run(
            [exe, "-w", str(out_path),
             "-s", str(_espeak_speed(voice_params.rate)),
             "-p", str(_espeak_pitch(voice_params.pitch)),
             "-a", str(_espeak_amp(voice_params.volume))],
            input=text.encode("utf-8"), check=True,
        )
        return out_path


def make_tts(engine: str, *, kokoro_model: str, kokoro_voices: str,
             chatterbox_refs: str = "", chatterbox_device: str = "cpu",
             chatterbox_model: str = "") -> TTSAdapter:
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
    if choice in ("espeak", "espeak-ng", "espeakng"):
        return EspeakNgAdapter()
    if choice == "kokoro":
        return KokoroAdapter(kokoro_model, kokoro_voices)
    if choice in ("chatterbox", "cb"):
        return ChatterboxAdapter(chatterbox_refs, chatterbox_device, chatterbox_model)
    # auto
    if Path(kokoro_model).exists() and Path(kokoro_voices).exists():
        try:
            return KokoroAdapter(kokoro_model, kokoro_voices)
        except Exception:
            pass
    return Pyttsx3Adapter()


# --- per-engine capability matrix ------------------------------------------
# Engines differ in which dials they render; this makes that explicit so cross-engine
# comparisons stay honest (e.g. pyttsx3 has no pitch, so its "pitch dial" is not testable).
_ENGINE_CLASSES = [MockTTSAdapter, Pyttsx3Adapter, Sapi5XmlAdapter, EspeakNgAdapter,
                   KokoroAdapter, ChatterboxAdapter]
_DIALS = ("rate", "volume", "pitch")


def capability_matrix() -> list[dict]:
    """One row per engine: which prosody dials it renders, whether it is a natural voice, and
    whether it accepts NATIVE emotion conditioning (emotion as input rather than as prosody).
    Keeps engine comparisons honest and drives the register flags."""
    rows = []
    for cls in _ENGINE_CLASSES:
        row = {"engine": cls.engine_id}
        row.update({d: ("yes" if d in cls.renders else "no") for d in _DIALS})
        row["natural"] = "yes" if cls.natural else "no"
        row["native_emotion"] = "yes" if cls.native_emotion else "no"
        row["note"] = cls.note
        rows.append(row)
    return rows


def format_capability_matrix() -> str:
    """Human-readable capability matrix table."""
    lines = [f"  {'engine':<11}{'rate':>6}{'volume':>8}{'pitch':>7}{'natural':>9}"
             f"{'native-emo':>12}   note",
             "  " + "-" * 92]
    for r in capability_matrix():
        lines.append(f"  {r['engine']:<11}{r['rate']:>6}{r['volume']:>8}{r['pitch']:>7}"
                     f"{r['natural']:>9}{r['native_emotion']:>12}   {r['note']}")
    return "\n".join(lines)
