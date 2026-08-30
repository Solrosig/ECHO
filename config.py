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

    # storage / output
    db_path: str = os.getenv("ECHO_DB", "echo.db")
    audio_dir: str = os.getenv("ECHO_AUDIO_DIR", "audio_out")

    # gate
    max_retries: int = int(os.getenv("ECHO_MAX_RETRIES", "2"))
    # G6: which EmotionJudge decides the emotion of a generated reply.
    # self-report (L0, legacy/leaky) | blind-llm (L1) | lexicon (L2, default)
    judge: str = os.getenv("ECHO_JUDGE", "lexicon")
    affect_norms: str = os.getenv("ECHO_AFFECT_NORMS", "")

    # evaluation — audible-duration band. Clips outside [min, max] are FLAGGED
    # (duration_ok=False), never silently altered, so the emotion signal stays intact.
    min_duration_s: float = float(os.getenv("ECHO_MIN_DURATION", "2.5"))
    max_duration_s: float = float(os.getenv("ECHO_MAX_DURATION", "15.0"))


def load_config() -> Config:
    return Config()
