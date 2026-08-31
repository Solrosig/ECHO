"""TTS adapter — PROTECTED SEAM #2 (speech side).

`synthesize(text, voice_params) -> Path` writes a WAV. Engines share one interface:
  - KokoroAdapter    : high-quality open-source neural TTS (rate + volume)
  - Sapi5XmlAdapter  : Windows SAPI5 via prosody XML — renders rate + volume + PITCH
  - Pyttsx3Adapter   : offline OS voice (rate + volume; no pitch) — safe fallback
  - ChatterboxAdapter: neural, NATIVE emotion conditioning (exaggeration + reference style)
  - ZipVoiceAdapter  : neural flow-matching, emotion via reference style; out-of-process
  - MockTTSAdapter   : dependency-free, for tests / offline integration runs

Voice dials arrive pre-computed on `voice_params` (rate, volume, pitch).
"""

from __future__ import annotations

import sys
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


def _zipvoice_speed(rate: float) -> float:
    """ECHO rate factor -> ZipVoice `--speed`.

    The conventions already agree (1.0 = normal, >1.0 = faster), so this is a pass-through
    with a clamp; ZipVoice accepts any float and extreme values degrade intelligibility.
    Note there is deliberately NO arousal->speed mapping here: `voice_params.rate` is
    already the strategy's arousal-derived dial, so deriving a second one from arousal
    would count the same signal twice and make ZipVoice non-comparable with Kokoro and
    eSpeak, which receive the same dial.
    """
    return round(max(0.5, min(2.0, rate)), 3)


class ZipVoiceAdapter(TTSAdapter):
    """ZipVoice (k2-fsa, Apache-2.0) — zero-shot flow-matching TTS, run OUT OF PROCESS.

    Admitted for a CONTROLLED COMPARISON. Phase X established that reference-clip
    conditioning is what finally carried emotion (Chatterbox Condition C: arousal 100 %,
    UTMOS 3.923), but that result came from one model, so it cannot distinguish a property
    of *the mechanism* from a property of *Chatterbox*. ZipVoice is conditioned on the same
    per-quadrant RAVDESS clips, over the same stimuli, with the same quadrant targets — so
    the only thing that varies is the model. Whatever survives that swap is a property of
    reference conditioning; whatever does not is a property of the engine.

    Emotion reaches the engine ONLY through the reference clip: ZipVoice exposes no
    expressiveness scalar and no emotion label, so `--prompt-wav` is the entire emotional
    channel. Rate is rendered natively via `--speed`; loudness is a post-scale, as elsewhere.

    THREE DESIGN CONSEQUENCES, each deliberate:

    1. OUT OF PROCESS. ZipVoice ships as a CLI module (`zipvoice.bin.infer_zipvoice`) and
       pins its own torch/k2/lhotse/vocos stack. Importing it into ECHO's interpreter would
       repeat the irreconcilable numpy conflict that already forced separate environments
       for Chatterbox. A subprocess with a configurable interpreter (`ECHO_ZIPVOICE_PYTHON`)
       lets ZipVoice keep its own venv and keeps ECHO's dependency graph unchanged.
    2. SEEDED. Flow matching samples from noise, so the engine is stochastic by nature and
       would fail the reproducibility filter. ZipVoice calls `fix_random_seed(--seed)`, so
       the seed is pinned explicitly here and recorded, rather than left at its default.
    3. A TRANSCRIPT IS REQUIRED. Zero-shot cloning needs `--prompt-text` as well as
       `--prompt-wav`; there is no default voice to fall back on. The transcript is read
       from `<refs_dir>/Q<n>.txt`, written by `make_ravdess_refs.py`.

    Known structural limitation, to be tested rather than assumed: ZipVoice RMS-normalises
    the prompt (`--target-rms`, default 0.1) before conditioning on it. The RAVDESS
    references carry a ~35x loudness range across quadrants (measured by check_refs.py), and
    that loudness IS an arousal cue — so normalisation may erase part of the arousal channel
    before the model ever sees it. Setting `--target-rms 0` disables it, which makes this a
    directly testable prediction rather than a caveat.
    """

    engine_id = "zipvoice"
    renders = frozenset({"rate", "volume"})   # speed natively; loudness as a post-scale
    natural = True
    native_emotion = True                     # emotion enters as a reference clip, not as dials
    note = "neural, Apache-2.0; flow matching; emotion via reference clip; out-of-process, seeded"

    #: files `--model-dir` must contain when a local checkpoint is used instead of the download
    MODEL_FILES = ("model.pt", "model.json", "tokens.txt")
    #: files `--vocoder-path` must contain. The vocoder is a SEPARATE Hugging Face repo
    #: (charactr/vocos-mel-24khz) fetched independently of the model, so a network that
    #: blocks the Hub blocks both and a local model directory alone is not enough.
    VOCODER_FILES = ("config.yaml", "pytorch_model.bin")
    #: pydub silence threshold hard-coded inside ZipVoice's `remove_silence`, in dBFS.
    #: A property of the engine, not something ECHO can configure.
    SILENCE_THRESH_DBFS = -50.0
    #: Below this share of audible 10 ms chunks, the prompt is destroyed rather than
    #: trimmed. 0.20 is well clear of the observed failure (Q4 at ~0.01) and of the
    #: quietest reference that worked (Q3, which renders normally).
    MIN_SURVIVING_FRACTION = 0.20

    def __init__(self, refs_dir: str = "refs_ravdess", python: str = "",
                 model_name: str = "zipvoice", model_dir: str = "", seed: int = 666,
                 num_step: int = 0, target_rms: float = 0.1, num_thread: int = 4,
                 repo: str = "", vocoder_dir: str = "", timeout_s: float = 900.0) -> None:
        self._refs_dir = refs_dir
        self._python = python or sys.executable
        self._model_name = model_name
        self._model_dir = model_dir
        self._seed = seed
        self._num_step = num_step          # 0 = leave ZipVoice's per-model default (16 / 8)
        self._target_rms = target_rms
        self._num_thread = num_thread
        self._repo = repo
        self._vocoder_dir = vocoder_dir
        self._timeout_s = timeout_s

    def _build_env(self) -> "dict[str, str] | None":
        """Environment for the subprocess, with the ZipVoice checkout on PYTHONPATH.

        ZipVoice ships **no `setup.py`** and a `pyproject.toml` containing only formatting
        configuration, so `pip install -r requirements.txt` installs its dependencies but
        never the package itself. Upstream expects `python -m zipvoice.bin.infer_zipvoice`
        to be run from the repository root, where the current directory is implicitly on
        `sys.path`. ECHO runs it from ECHO's directory, so the package is invisible and the
        module lookup fails.

        PYTHONPATH is used rather than `cwd=<repo>` deliberately: changing the working
        directory would silently re-base every relative path ECHO passes — the reference
        clip and the output file — onto the ZipVoice checkout. Paths are resolved to
        absolute as well, so neither mechanism can misfire, but only one of the two changes
        the meaning of the caller's arguments and it is not this one.
        """
        if not self._repo:
            return None                    # rely on the interpreter finding zipvoice itself
        import os

        env = dict(os.environ)
        existing = env.get("PYTHONPATH", "")
        repo = str(Path(self._repo).resolve())
        env["PYTHONPATH"] = repo + (os.pathsep + existing if existing else "")
        return env

    def _reference_for(self, quadrant: str) -> "tuple[str, str] | None":
        """Return (wav_path, transcript) for a quadrant, or None if the clip is absent.

        Unlike Chatterbox, a missing reference is NOT a degraded mode — ZipVoice has no
        default voice, so the caller must treat None as fatal.
        """
        if not self._refs_dir or not quadrant:
            return None
        wav = Path(self._refs_dir) / f"{quadrant}.wav"
        if not wav.exists():
            return None
        txt = wav.with_suffix(".txt")
        if not txt.exists():
            raise RuntimeError(
                f"ZipVoice needs a transcript for its reference clip, but {txt} is missing. "
                "Re-run `python make_ravdess_refs.py --ravdess <folder> --actor <n>`, which "
                "writes Q1.txt..Q4.txt beside the clips, or create the file containing the "
                "exact words spoken in the clip."
            )
        return str(wav), txt.read_text(encoding="utf-8").strip()

    def _assert_reference_is_audible(self, ref_wav: str, quadrant: str) -> None:
        """Refuse a reference ZipVoice will delete as silence.

        Measured 2026-08-31: ZipVoice preprocesses the prompt with
        `remove_silence(..., silence_thresh=-50)` — a pydub gate with an ABSOLUTE threshold,
        applied BEFORE any normalisation. The RAVDESS Q4 'calm' reference sits at about
        -52 dBFS RMS because low arousal is quiet, so the engine discarded almost all of it
        and emitted 0.10-0.21 s for every Q4 stimulus, in both rendered conditions. The
        register recorded that only as `duration_ok=no`, which describes the symptom and
        hides the cause.

        `--target-rms 0` cannot help, because the gate runs first. The fix is a level-matched
        reference set (`make_matched_refs.py`), and the point of failing here is that a
        clip of 0.1 s is not a bad synthesis result — it is an absent one, and it must not
        reach the corpus wearing the same row shape as a real measurement.
        """
        try:
            import numpy as np
            import soundfile as sf
        except Exception:
            return                                   # cannot check; do not block the render
        try:
            x, sr = sf.read(ref_wav, dtype="float32")
        except Exception:
            return
        if x.ndim > 1:
            x = x.mean(axis=1)
        n = max(1, sr // 100)                        # pydub scans in 10 ms chunks
        usable = (len(x) // n) * n
        if usable == 0:
            return
        rms = np.sqrt((x[:usable].reshape(-1, n).astype("float64") ** 2).mean(axis=1))
        surviving = float((rms > 10 ** (self.SILENCE_THRESH_DBFS / 20.0)).mean())
        if surviving >= self.MIN_SURVIVING_FRACTION:
            return
        raise RuntimeError(
            f"Reference clip for {quadrant or '(no quadrant)'} is too quiet for ZipVoice: only "
            f"{surviving * 100:.0f}% of it is above the engine's {self.SILENCE_THRESH_DBFS:.0f} "
            f"dBFS silence gate ({ref_wav}).\n"
            "ZipVoice strips that as silence BEFORE normalising, so it would condition on "
            "almost nothing and emit a fraction of a second of audio. Setting "
            "ECHO_ZIPVOICE_TARGET_RMS=0 does not help — the gate runs first.\n"
            "Fix:  python make_matched_refs.py\n"
            "      set ECHO_ZIPVOICE_REFS=refs_ravdess_matched\n"
            "Note that level-matching removes the between-quadrant loudness difference, which "
            "is part of the arousal cue, and must be declared wherever the resulting clips "
            "are reported."
        )

    def _build_command(self, text: str, ref_wav: str, ref_text: str,
                       speed: float, out_path: Path) -> list[str]:
        """Assemble the CLI invocation. Kept separate from `synthesize` so the command —
        the part that carries every experimental parameter — is testable without a model."""
        if self._repo:
            repo = Path(self._repo)
            if not (repo / "zipvoice").is_dir():
                raise RuntimeError(
                    f"ECHO_ZIPVOICE_REPO points at '{repo}', which has no 'zipvoice' folder. "
                    "It must be the root of the cloned repository — the directory containing "
                    "the 'zipvoice' package and requirements.txt."
                )
        # Absolute paths: the subprocess is another process with its own notion of 'here',
        # and ECHO passes relative paths (refs_ravdess/Q1.wav, research/...).
        cmd = [self._python, "-m", "zipvoice.bin.infer_zipvoice",
               "--model-name", self._model_name,
               "--prompt-wav", str(Path(ref_wav).resolve()),
               "--prompt-text", ref_text,
               "--text", text,
               "--res-wav-path", str(out_path.resolve()),
               "--speed", str(speed),
               "--seed", str(self._seed),                  # reproducibility (T0.3)
               "--target-rms", str(self._target_rms),
               "--num-thread", str(self._num_thread)]
        if self._num_step:
            cmd += ["--num-step", str(self._num_step)]
        if self._model_dir:
            local = Path(self._model_dir)
            missing = [f for f in self.MODEL_FILES if not (local / f).exists()]
            if missing:
                raise RuntimeError(
                    f"ZipVoice model dir '{local}' is missing: {missing}. Download them once "
                    "from https://huggingface.co/k2-fsa/ZipVoice (folder 'zipvoice/'), or "
                    "clear ECHO_ZIPVOICE_MODEL_DIR to let ZipVoice fetch them itself."
                )
            cmd += ["--model-dir", str(local)]
        if self._vocoder_dir:
            voc = Path(self._vocoder_dir)
            missing = [f for f in self.VOCODER_FILES if not (voc / f).exists()]
            if missing:
                raise RuntimeError(
                    f"ZipVoice vocoder dir '{voc}' is missing: {missing}. Download them once "
                    "from https://huggingface.co/charactr/vocos-mel-24khz/tree/main, or clear "
                    "ECHO_ZIPVOICE_VOCODER to let ZipVoice fetch the vocoder itself."
                )
            cmd += ["--vocoder-path", str(voc.resolve())]
        return cmd

    def synthesize(self, text: str, voice_params: VoiceParams, out_path: Path) -> Path:
        import subprocess

        out_path.parent.mkdir(parents=True, exist_ok=True)
        ref = self._reference_for(voice_params.quadrant)
        if ref is None:
            raise RuntimeError(
                f"ZipVoice has no default voice: it needs a reference clip for quadrant "
                f"'{voice_params.quadrant}', expected at "
                f"{Path(self._refs_dir) / (voice_params.quadrant + '.wav')}. Build the set with "
                "`python make_ravdess_refs.py --ravdess <folder> --actor <n>` and point "
                "ECHO_ZIPVOICE_REFS at it."
            )
        ref_wav, ref_text = ref
        self._assert_reference_is_audible(ref_wav, voice_params.quadrant)
        cmd = self._build_command(text, ref_wav, ref_text,
                                  _zipvoice_speed(voice_params.rate), out_path)
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True,
                                  timeout=self._timeout_s, env=self._build_env())
        except FileNotFoundError as exc:
            raise RuntimeError(
                f"Could not start the ZipVoice interpreter '{self._python}'. Install ZipVoice "
                "in its own environment (git clone https://github.com/k2-fsa/ZipVoice, "
                "pip install -r requirements.txt) and set ECHO_ZIPVOICE_PYTHON to that "
                "environment's python executable."
            ) from exc
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(
                f"ZipVoice exceeded {self._timeout_s:.0f}s on one clip. On CPU, try "
                "--model-name zipvoice_distill (ECHO_ZIPVOICE_MODEL) and raise "
                "ECHO_ZIPVOICE_THREADS."
            ) from exc
        if proc.returncode != 0:
            output = (proc.stderr or proc.stdout or "")
            tail = output.strip().splitlines()[-15:]
            hint = ""
            if "TorchCodec is required" in output or "torchcodec" in output:
                # torchaudio 2.11 removed its own audio backends and delegates decoding to
                # torchcodec. ZipVoice's requirements.txt does not pin torchaudio, so pip
                # resolves to a version whose loader is not self-contained.
                hint = ("\n\ntorchaudio 2.11+ delegates audio loading to torchcodec, which "
                        "ZipVoice's unpinned requirements never install. In the ZipVoice "
                        "environment:\n"
                        "  pip install torchcodec\n"
                        "If torchcodec will not build (it needs FFmpeg libraries), pin the "
                        "older pair whose loader is self-contained instead:\n"
                        "  pip install \"torch==2.5.1\" \"torchaudio==2.5.1\"")
            elif "LocalEntryNotFoundError" in output or "we cannot find the requested files" in output:
                # Hugging Face is unreachable. Seen on this network for the SER model and
                # for Chatterbox as well, so it is the environment rather than the engine.
                hint = ("\n\nHugging Face could not be reached and nothing is cached, so the "
                        "model was never downloaded. Two ways round it, in order of effort:\n"
                        "  1) set HF_ENDPOINT=https://hf-mirror.com   (the mirror ZipVoice "
                        "itself recommends), then re-run;\n"
                        "  2) download both repos once in a BROWSER and point ECHO at them:\n"
                        "       https://huggingface.co/k2-fsa/ZipVoice  -> zipvoice/ folder: "
                        f"{', '.join(self.MODEL_FILES)}\n"
                        "       https://huggingface.co/charactr/vocos-mel-24khz -> "
                        f"{', '.join(self.VOCODER_FILES)}\n"
                        "     then  set ECHO_ZIPVOICE_MODEL_DIR=zv_model\n"
                        "           set ECHO_ZIPVOICE_VOCODER=zv_vocoder\n"
                        "   The vocoder is a SEPARATE repo, so a local model folder alone is "
                        "not enough when the Hub is blocked.")
            elif "No module named 'zipvoice'" in output or "No module named zipvoice" in output:
                # The commonest failure, and it is not a broken install: ZipVoice ships no
                # setup.py, so its package is never placed on the interpreter's path.
                hint = ("\n\nZipVoice's dependencies are installed but the package itself is "
                        "not on the path — it ships no setup.py, so pip never installs it. "
                        "Point ECHO at the checkout:\n"
                        "  set ECHO_ZIPVOICE_REPO=C:\\path\\to\\ZipVoice")
            raise RuntimeError("ZipVoice failed (exit %d):\n  %s%s"
                               % (proc.returncode, "\n  ".join(tail), hint))
        if not out_path.exists():
            raise RuntimeError(
                f"ZipVoice reported success but wrote no file at {out_path}."
            )

        # Post-process, ALWAYS — two jobs in one read/write pass.
        #
        # 1. FORMAT NORMALISATION. `torchaudio.save` writes float32 WAV (format code 3).
        #    Every other engine in this project ends up 16-bit PCM: espeak/SAPI/pyttsx3
        #    natively, and Kokoro/Chatterbox because `soundfile.write` defaults float input
        #    to PCM_16. Leaving ZipVoice as the one float32 engine would put a container
        #    difference alongside the engine difference in a corpus whose entire purpose is
        #    cross-engine comparison — and Python's `wave` module, which synth_stimuli.py
        #    uses for duration, cannot read float WAV at all, so every ZipVoice clip would
        #    be flagged duration_ok=False for a reason that has nothing to do with the audio.
        #    This converts the CONTAINER, not the signal.
        #
        # 2. LOUDNESS post-scale, applied AFTER the engine's own RMS normalisation — so the
        #    dial sets relative level between clips; it does not restore the reference's
        #    dynamics, which ZipVoice normalised away before conditioning.
        import soundfile as sf

        samples, sample_rate = sf.read(str(out_path), dtype="float32")
        samples = samples * max(0.0, min(1.0, voice_params.volume))
        sf.write(str(out_path), samples, sample_rate, subtype="PCM_16")
        return out_path


class SubprocessTTSAdapter(TTSAdapter):
    """Base for research engines that ship as a repository rather than a package.

    ZipVoice taught the pattern the hard way (2026-08-31): five undeclared
    dependencies, no `setup.py`, weights split across two Hugging Face repos, and an
    unpinned torchaudio that changed its audio backend. StyleTTS 2, CosyVoice 2 and
    Parler-TTS are the same kind of artefact — research code published to be *cloned*,
    not installed — so the same five defences apply to all of them:

      1. **Own interpreter.** Each engine pins its own torch stack; running it in ECHO's
         process would repeat the numpy conflict that already forced separate environments.
      2. **Checkout on PYTHONPATH.** No `setup.py` means pip never installs the package,
         and upstream expects to be run from the repo root. PYTHONPATH rather than `cwd`,
         so relative paths ECHO passes are not silently re-based.
      3. **Local weights.** The Hugging Face hub is blocked on this network; every engine
         needs a `--model-dir` escape hatch.
      4. **Absolute paths.** A subprocess has its own notion of "here".
      5. **PCM-16 output.** Engines write float32 or odd rates; the corpus must be one
         container, or a format difference sits alongside the engine difference.

    **The command is a TEMPLATE in configuration, not code.** Research CLIs change between
    commits, and hard-coding one means a code change and a test run every time upstream
    moves. The template uses named placeholders — {python} {text} {out} {ref_wav}
    {ref_text} {speed} {seed} {instruction} {model_dir} — so an engine can be re-pointed
    from `.env` without touching Python. Unknown placeholders are left untouched rather
    than raising, so a template written for a future flag degrades to a visible literal in
    the command instead of an exception three layers down.
    """

    engine_id = "subprocess-base"
    natural = True
    #: files the local model directory must contain; empty means no check
    MODEL_FILES: tuple = ()

    def __init__(self, template: str = "", python: str = "", repo: str = "",
                 model_dir: str = "", refs_dir: str = "", seed: int = 0,
                 timeout_s: float = 900.0) -> None:
        self._template = template
        self._python = python or sys.executable
        self._repo = repo
        self._model_dir = model_dir
        self._refs_dir = refs_dir
        self._seed = seed
        self._timeout_s = timeout_s

    # -- subclass hooks ----------------------------------------------------
    def emotion_fields(self, voice_params: VoiceParams) -> dict:
        """Engine-specific placeholders. Overridden per control mechanism."""
        return {}

    # -- shared machinery --------------------------------------------------
    def _env(self) -> "dict[str, str] | None":
        if not self._repo:
            return None
        import os

        env = dict(os.environ)
        repo = str(Path(self._repo).resolve())
        existing = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = repo + (os.pathsep + existing if existing else "")
        return env

    def _check_model_dir(self) -> None:
        if not (self._model_dir and self.MODEL_FILES):
            return
        local = Path(self._model_dir)
        missing = [f for f in self.MODEL_FILES if not (local / f).exists()]
        if missing:
            raise RuntimeError(
                f"{self.engine_id} model dir '{local}' is missing: {missing}. Download them "
                "once in a browser, or clear the model-dir setting to let the engine fetch them."
            )

    def build_command(self, text: str, voice_params: VoiceParams, out_path: Path) -> list[str]:
        """Render the template into an argv list. Pure — testable without the engine."""
        import shlex

        if not self._template:
            raise RuntimeError(
                f"No command template configured for {self.engine_id}. Set it in .env "
                f"(see .env.example) — research CLIs change, so the invocation is "
                f"configuration rather than code."
            )
        self._check_model_dir()
        fields = {
            "python": self._python,
            "text": text,
            "out": str(out_path.resolve()),
            "seed": str(self._seed),
            "model_dir": str(Path(self._model_dir).resolve()) if self._model_dir else "",
            "speed": str(round(max(0.5, min(2.0, voice_params.rate)), 3)),
        }
        fields.update(self.emotion_fields(voice_params))
        # shlex.split first, then substitute per token: a placeholder whose value contains
        # spaces (reply text, an instruction sentence) must stay ONE argv element.
        out = []
        for tok in shlex.split(self._template, posix=False):
            for key, val in fields.items():
                tok = tok.replace("{" + key + "}", val)
            out.append(tok.strip('"'))
        return [t for t in out if t != ""]

    def synthesize(self, text: str, voice_params: VoiceParams, out_path: Path) -> Path:
        import subprocess

        out_path.parent.mkdir(parents=True, exist_ok=True)
        cmd = self.build_command(text, voice_params, out_path)
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True,
                                  timeout=self._timeout_s, env=self._env())
        except FileNotFoundError as exc:
            raise RuntimeError(
                f"Could not start the {self.engine_id} interpreter '{self._python}'. Install "
                f"the engine in its own environment and point ECHO at that python."
            ) from exc
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(f"{self.engine_id} exceeded {self._timeout_s:.0f}s on one clip.") from exc
        if proc.returncode != 0:
            output = proc.stderr or proc.stdout or ""
            tail = output.strip().splitlines()[-15:]
            hint = ""
            if "No module named" in output:
                hint = ("\n\nIf the missing module is the engine itself, it ships no "
                        "setup.py — point ECHO at the checkout so it goes on PYTHONPATH.")
            elif "LocalEntryNotFoundError" in output or "cannot find the requested files" in output:
                hint = ("\n\nHugging Face is unreachable. Try HF_ENDPOINT=https://hf-mirror.com, "
                        "or download the weights in a browser and set the model-dir.")
            elif "torchcodec" in output:
                hint = ("\n\ntorchaudio 2.11+ delegates decoding to torchcodec. In the engine's "
                        "environment: pip install torchcodec — or pin torch/torchaudio 2.5.1.")
            raise RuntimeError("%s failed (exit %d):\n  %s%s"
                               % (self.engine_id, proc.returncode, "\n  ".join(tail), hint))
        if not out_path.exists():
            raise RuntimeError(f"{self.engine_id} reported success but wrote no file at {out_path}.")

        import soundfile as sf                       # one container for the whole corpus

        samples, sample_rate = sf.read(str(out_path), dtype="float32")
        samples = samples * max(0.0, min(1.0, voice_params.volume))
        sf.write(str(out_path), samples, sample_rate, subtype="PCM_16")
        return out_path


class StyleTTS2Adapter(SubprocessTTSAdapter):
    """StyleTTS 2 (MIT; Li et al., NeurIPS 2023) — emotion via an explicit STYLE VECTOR.

    Mechanism 4 of the taxonomy, and the only engine in the set with a peer-reviewed
    venue. Its style vector may be *extracted* from reference audio or *sampled* from a
    diffusion model — so it is the one engine that can produce a style ECHO never supplied,
    which makes it the natural third member of the reference-conditioning family and a
    bridge to the instruction family.
    """

    engine_id = "styletts2"
    renders = frozenset({"rate", "volume"})
    native_emotion = True
    note = "neural, MIT, peer-reviewed (NeurIPS 2023); explicit style vector, diffusion-sampled or reference-extracted"

    def emotion_fields(self, voice_params: VoiceParams) -> dict:
        ref = ""
        if self._refs_dir and voice_params.quadrant:
            cand = Path(self._refs_dir) / f"{voice_params.quadrant}.wav"
            if cand.exists():
                ref = str(cand.resolve())
        return {"ref_wav": ref, "quadrant": voice_params.quadrant or ""}


#: Natural-language emotion instructions, one per quadrant. These are the ENTIRE emotional
#: channel for instruction-conditioned engines — the wording is the experimental
#: manipulation, so it is defined here, versioned, and reported, not typed at a prompt.
#: Phrasing follows the circumplex definition of each quadrant rather than a bare emotion
#: word, so that valence and arousal are both stated and the instruction cannot be read as
#: a single categorical label.
QUADRANT_INSTRUCTIONS = {
    "Q1": "Speak in a happy, upbeat and energetic tone.",
    "Q2": "Speak in an angry, agitated and tense tone.",
    "Q3": "Speak in a sad, subdued and downhearted tone.",
    "Q4": "Speak in a calm, warm and relaxed tone.",
}
INSTRUCTION_VERSION = "instructions-v1"


class InstructionTTSAdapter(SubprocessTTSAdapter):
    """Shared base for engines whose emotional channel is a SENTENCE OF ENGLISH.

    Mechanism 5, and the last untested channel for valence in this project. Every other
    mechanism measured so far routes emotion through *acoustics*; this one routes it through
    *semantics*, which is why it can succeed where four acoustic mechanisms failed — or, by
    failing too, close the argument that the limit is the channel rather than the control.
    """

    renders = frozenset({"volume"})    # loudness post-scale only; no prosodic dials
    native_emotion = True

    def emotion_fields(self, voice_params: VoiceParams) -> dict:
        # A reference clip is optional here and means something different from mechanism 3:
        # it fixes WHO speaks, so that the instruction is the only thing carrying emotion.
        # CosyVoice 2 requires one; Parler-TTS names its speaker in the description instead.
        ref = ""
        if self._refs_dir and voice_params.quadrant:
            cand = Path(self._refs_dir) / f"{voice_params.quadrant}.wav"
            if cand.exists():
                ref = str(cand.resolve())
        return {"instruction": QUADRANT_INSTRUCTIONS.get(voice_params.quadrant, ""),
                "ref_wav": ref,
                "quadrant": voice_params.quadrant or ""}


class CosyVoice2Adapter(InstructionTTSAdapter):
    """CosyVoice 2 (FunAudioLLM, Apache-2.0 on the 0.5B checkpoint; arXiv:2412.10117)."""

    engine_id = "cosyvoice2"
    note = "neural, Apache-2.0; LLM + flow matching; emotion via natural-language instruction"


class ParlerTTSAdapter(InstructionTTSAdapter):
    """Parler-TTS (Apache-2.0) — emotion via a natural-language style DESCRIPTION.

    Admitted alongside CosyVoice 2 rather than instead of it: one engine cannot separate
    'the mechanism works' from 'this model works', so mechanism 5 needs two engines to make
    a claim at all — the same reasoning that admitted ZipVoice beside Chatterbox.
    """

    engine_id = "parlertts"
    note = "neural, Apache-2.0; emotion via natural-language style description"


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
             chatterbox_model: str = "", zipvoice_refs: str = "refs_ravdess",
             zipvoice_python: str = "", zipvoice_model: str = "zipvoice",
             zipvoice_model_dir: str = "", zipvoice_seed: int = 666,
             zipvoice_num_step: int = 0, zipvoice_target_rms: float = 0.1,
             zipvoice_threads: int = 4, zipvoice_repo: str = "",
             zipvoice_vocoder: str = "", cfg=None) -> TTSAdapter:
    """Select an engine.

    'mock' | 'pyttsx3' | 'sapi' (=sapi5xml, renders pitch) | 'espeak' | 'kokoro' |
    'chatterbox' | 'zipvoice' | 'auto'.
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
    if choice in ("styletts2", "styletts", "st2", "cosyvoice2", "cosyvoice", "cv2",
                  "parlertts", "parler"):
        if cfg is None:
            from config import load_config
            cfg = load_config()
        spec = {
            "styletts2": (StyleTTS2Adapter, "styletts2", True),
            "cosyvoice2": (CosyVoice2Adapter, "cosyvoice2", True),
            "parlertts": (ParlerTTSAdapter, "parlertts", False),
        }
        key = ({"styletts": "styletts2", "st2": "styletts2", "cosyvoice": "cosyvoice2",
                "cv2": "cosyvoice2", "parler": "parlertts"}).get(choice, choice)
        cls, prefix, wants_refs = spec[key]
        return cls(template=getattr(cfg, prefix + "_cmd"),
                   python=getattr(cfg, prefix + "_python"),
                   repo=getattr(cfg, prefix + "_repo"),
                   model_dir=getattr(cfg, prefix + "_model_dir"),
                   refs_dir=getattr(cfg, prefix + "_refs", "") if wants_refs else "",
                   seed=getattr(cfg, "engine_seed", 666))
    if choice in ("zipvoice", "zv"):
        return ZipVoiceAdapter(zipvoice_refs, zipvoice_python, zipvoice_model,
                               zipvoice_model_dir, zipvoice_seed, zipvoice_num_step,
                               zipvoice_target_rms, zipvoice_threads, zipvoice_repo,
                               zipvoice_vocoder)
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
                   KokoroAdapter, ChatterboxAdapter, ZipVoiceAdapter,
                   StyleTTS2Adapter, CosyVoice2Adapter, ParlerTTSAdapter]
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
