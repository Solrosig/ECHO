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

    # storage / output
    db_path: str = os.getenv("ECHO_DB", "echo.db")
    audio_dir: str = os.getenv("ECHO_AUDIO_DIR", "audio_out")

    # gate
    max_retries: int = int(os.getenv("ECHO_MAX_RETRIES", "2"))


def load_config() -> Config:
    return Config()
