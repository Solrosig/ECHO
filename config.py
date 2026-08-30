"""Central configuration. Nothing model/path/port is hard-coded elsewhere."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Config:
    # LLM (Ollama, OpenAI-compatible endpoint)
    ollama_host: str = os.getenv("ECHO_OLLAMA_HOST", "http://localhost:11434/v1")
    ollama_model: str = os.getenv("ECHO_OLLAMA_MODEL", "llama3.2:3b")
    llm_temperature: float = float(os.getenv("ECHO_LLM_TEMPERATURE", "0.7"))
    llm_timeout_s: float = float(os.getenv("ECHO_LLM_TIMEOUT", "60"))

    # TTS
    tts_engine: str = os.getenv("ECHO_TTS_ENGINE", "auto")  # auto | kokoro | pyttsx3
    kokoro_model_path: str = os.getenv("ECHO_KOKORO_MODEL", "kokoro-v1.0.onnx")
    kokoro_voices_path: str = os.getenv("ECHO_KOKORO_VOICES", "voices-v1.0.bin")
    kokoro_voice: str = os.getenv("ECHO_KOKORO_VOICE", "af_heart")
    # Chatterbox (native-emotion engine): optional folder with per-quadrant reference clips
    # Q1.wav..Q4.wav — the channel through which VALENCE is conditioned (style transfer).
    chatterbox_refs: str = os.getenv("ECHO_CHATTERBOX_REFS", "refs")
    chatterbox_device: str = os.getenv("ECHO_CHATTERBOX_DEVICE", "cpu")
    # local model folder (browser-downloaded) used when the HF download is blocked
    chatterbox_model: str = os.getenv("ECHO_CHATTERBOX_MODEL", "cb_model")
    # ZipVoice (k2-fsa, Apache-2.0): the CONTROLLED COMPARISON against Chatterbox
    # Condition C — same per-quadrant RAVDESS references, different model, so the Phase-X
    # result can be attributed to the mechanism or to the engine. Defaults point at
    # refs_ravdess because ZipVoice has NO default voice: without a reference clip and its
    # transcript it cannot synthesise at all.
    zipvoice_refs: str = os.getenv("ECHO_ZIPVOICE_REFS", "refs_ravdess")
    # ZipVoice pins its own torch/k2/lhotse stack, so it runs OUT OF PROCESS in its own
    # environment; point this at that environment's interpreter. Empty = this interpreter.
    zipvoice_python: str = os.getenv("ECHO_ZIPVOICE_PYTHON", "")
    zipvoice_model: str = os.getenv("ECHO_ZIPVOICE_MODEL", "zipvoice")  # or zipvoice_distill
    zipvoice_model_dir: str = os.getenv("ECHO_ZIPVOICE_MODEL_DIR", "")  # local ckpt if HF blocked
    # Flow matching samples from noise. The seed is pinned and RECORDED so clips can be
    # re-rendered byte-for-byte; 666 is ZipVoice's own default, kept so runs match the
    # published configuration unless deliberately varied.
    zipvoice_seed: int = int(os.getenv("ECHO_ZIPVOICE_SEED", "666"))
    zipvoice_num_step: int = int(os.getenv("ECHO_ZIPVOICE_STEPS", "0"))  # 0 = model default
    # ZipVoice RMS-normalises the PROMPT before conditioning (default 0.1). The RAVDESS
    # references span a ~35x loudness range across quadrants and that loudness is an arousal
    # cue, so normalisation may erase part of the arousal channel. Set 0 to disable — the
    # A/B that tests this prediction.
    zipvoice_target_rms: float = float(os.getenv("ECHO_ZIPVOICE_TARGET_RMS", "0.1"))
    zipvoice_threads: int = int(os.getenv("ECHO_ZIPVOICE_THREADS", "4"))

    # storage / output
    db_path: str = os.getenv("ECHO_DB", "echo.db")
    audio_dir: str = os.getenv("ECHO_AUDIO_DIR", "audio_out")

    # gate
    max_retries: int = int(os.getenv("ECHO_MAX_RETRIES", "2"))
    # G6: which EmotionJudge decides the emotion of a generated reply.
    # self-report (L0, legacy/leaky) | blind-llm (L1) | lexicon (L2, default)
    # cascade = lexicon (L2, independent) with the blinded LLM (L1) as fallback when the
    # lexicon has no rated vocabulary for a reply. Measured 2026-08-30: lexicon alone
    # abstains on ~12% of real replies even with the full Warriner norms, and an
    # abstention fails the gate and burns the retry budget.
    judge: str = os.getenv("ECHO_JUDGE", "cascade")
    # Warriner, Kuperman & Brysbaert (2013) norms, 13,915 lemmas, as published
    # (BRM-emot-submit.csv). Falls back to the small built-in table if absent -- which is
    # NOT usable for a reported result; run check_norms.py to verify.
    affect_norms: str = os.getenv("ECHO_AFFECT_NORMS", "BRM-emot-submit.csv")

    # evaluation — audible-duration band. Clips outside [min, max] are FLAGGED
    # (duration_ok=False), never silently altered, so the emotion signal stays intact.
    min_duration_s: float = float(os.getenv("ECHO_MIN_DURATION", "2.5"))
    max_duration_s: float = float(os.getenv("ECHO_MAX_DURATION", "15.0"))


def load_config() -> Config:
    return Config()
