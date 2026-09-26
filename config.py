"""Central configuration. Nothing model/path/port is hard-coded elsewhere.

Settings come from the environment and from an optional `.env` file beside this module.
Real environment variables win, so a one-off override is one `set` away.

Why a file: settings typed with `set` exist only in that terminal, so the run cannot be
reproduced. On 2026-08-31 a render in a fresh terminal silently lost ECHO_ZIPVOICE_PYTHON
and ECHO_ZIPVOICE_REPO and failed, although they had been set correctly twice before.
A file can be read, diffed and recorded in the session log with the results.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _load_dotenv(path: "Path | None" = None) -> None:
    """Read KEY=VALUE lines from `.env` into the environment without overwriting.

    Not python-dotenv: every module imports this one, and fifteen lines beat a new
    dependency. Skips blank lines and `#` comments, strips surrounding quotes, and ignores
    malformed lines so a settings typo cannot stop the system from starting.
    """
    env_path = path or Path(__file__).resolve().parent / ".env"
    try:
        text = env_path.read_text(encoding="utf-8")
    except Exception:
        return
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip().strip('"').strip("'")
        if key and key not in os.environ:      # a real env var always wins
            os.environ[key] = value


_load_dotenv()


@dataclass(frozen=True)
class Config:
    # LLM (Ollama, OpenAI-compatible endpoint)
    ollama_host: str = os.getenv("ECHO_OLLAMA_HOST", "http://localhost:11434/v1")
    ollama_model: str = os.getenv("ECHO_OLLAMA_MODEL", "llama3.2:3b")
    llm_temperature: float = float(os.getenv("ECHO_LLM_TEMPERATURE", "0.7"))
    llm_timeout_s: float = float(os.getenv("ECHO_LLM_TIMEOUT", "60"))

    # TTS
    tts_engine: str = os.getenv("ECHO_TTS_ENGINE", "auto")  # auto or a name from tts.make_tts
    kokoro_model_path: str = os.getenv("ECHO_KOKORO_MODEL", "kokoro-v1.0.onnx")
    kokoro_voices_path: str = os.getenv("ECHO_KOKORO_VOICES", "voices-v1.0.bin")
    kokoro_voice: str = os.getenv("ECHO_KOKORO_VOICE", "af_heart")
    # Chatterbox (native emotion): optional folder of per-quadrant reference clips
    # Q1.wav..Q4.wav, the style-transfer channel that conditions valence.
    chatterbox_refs: str = os.getenv("ECHO_CHATTERBOX_REFS", "refs")
    chatterbox_device: str = os.getenv("ECHO_CHATTERBOX_DEVICE", "cpu")
    # local model folder (browser-downloaded) used when the HF download is blocked
    chatterbox_model: str = os.getenv("ECHO_CHATTERBOX_MODEL", "cb_model")
    # ZipVoice (k2-fsa, Apache-2.0): controlled comparison with Chatterbox Condition C.
    # Same per-quadrant RAVDESS references, different model, so the Phase-X result can be
    # attributed to the mechanism or to the engine. Defaults to refs_ravdess because
    # ZipVoice has no default voice: it cannot synthesise without a reference clip and its
    # transcript.
    zipvoice_refs: str = os.getenv("ECHO_ZIPVOICE_REFS", "refs_ravdess")
    # ZipVoice pins its own torch/k2/lhotse stack, so it runs out of process in its own
    # environment; set this to that environment's interpreter. Empty = this interpreter.
    zipvoice_python: str = os.getenv("ECHO_ZIPVOICE_PYTHON", "")
    zipvoice_model: str = os.getenv("ECHO_ZIPVOICE_MODEL", "zipvoice")  # or zipvoice_distill
    zipvoice_model_dir: str = os.getenv("ECHO_ZIPVOICE_MODEL_DIR", "")  # local ckpt if HF blocked
    # Flow matching samples from noise, so the seed is pinned and recorded for byte-for-byte
    # re-renders. 666 is ZipVoice's own default, so runs match the published configuration
    # unless varied on purpose.
    zipvoice_seed: int = int(os.getenv("ECHO_ZIPVOICE_SEED", "666"))
    zipvoice_num_step: int = int(os.getenv("ECHO_ZIPVOICE_STEPS", "0"))  # 0 = model default
    # ZipVoice RMS-normalises the prompt before conditioning (default 0.1). The RAVDESS
    # references span a ~35x loudness range across quadrants, and loudness is an arousal
    # cue, so normalisation may erase part of the arousal channel. 0 disables it (the A/B
    # that tests this prediction).
    zipvoice_target_rms: float = float(os.getenv("ECHO_ZIPVOICE_TARGET_RMS", "0.1"))
    zipvoice_threads: int = int(os.getenv("ECHO_ZIPVOICE_THREADS", "4"))
    # ZipVoice checkout, put on PYTHONPATH. It has no setup.py (pyproject.toml holds only
    # formatting config), so `pip install -r requirements.txt` never installs the package.
    # Upstream runs it from the repo root, where cwd is on sys.path; ECHO runs it elsewhere.
    zipvoice_repo: str = os.getenv("ECHO_ZIPVOICE_REPO", "")
    # The vocoder (charactr/vocos-mel-24khz) is a separate Hugging Face repo, so a blocked
    # Hub blocks both and a local model folder alone is not enough. When the network
    # intercepts TLS, download both in a browser.
    zipvoice_vocoder: str = os.getenv("ECHO_ZIPVOICE_VOCODER", "")

    # --- Engines that ship as repositories, not packages ---
    # Their CLIs change between commits, so the invocation is a template in .env, not code.
    # Placeholders: {python} {text} {out} {ref_wav} {instruction} {speed} {seed}
    # {model_dir} {quadrant}. See .env.example and SubprocessTTSAdapter.
    # Default templates call the bundled runners in runners/. None of these three engines
    # ships a CLI (all are Python APIs), so a blank template would leave the adapter unable
    # to run. The runner is the CLI, runs in the engine's own interpreter, and is the one
    # place to change when an upstream API moves.
    # StyleTTS 2: mechanism 4, explicit style vector (MIT, NeurIPS 2023)
    styletts2_cmd: str = os.getenv(
        "ECHO_STYLETTS2_CMD",
        '{python} runners/styletts2_run.py --text "{text}" --out {out} '
        '--ref-wav "{ref_wav}" --seed {seed}')
    styletts2_python: str = os.getenv("ECHO_STYLETTS2_PYTHON", "")
    styletts2_repo: str = os.getenv("ECHO_STYLETTS2_REPO", "")
    styletts2_model_dir: str = os.getenv("ECHO_STYLETTS2_MODEL_DIR", "")
    styletts2_refs: str = os.getenv("ECHO_STYLETTS2_REFS", "refs_ravdess_matched")
    # CosyVoice 2: mechanism 5, natural-language instruction (Apache-2.0)
    cosyvoice2_cmd: str = os.getenv(
        "ECHO_COSYVOICE2_CMD",
        '{python} runners/cosyvoice2_run.py --text "{text}" --out {out} '
        '--instruction "{instruction}" --ref-wav "{ref_wav}" --seed {seed}')
    cosyvoice2_python: str = os.getenv("ECHO_COSYVOICE2_PYTHON", "")
    cosyvoice2_repo: str = os.getenv("ECHO_COSYVOICE2_REPO", "")
    cosyvoice2_model_dir: str = os.getenv("ECHO_COSYVOICE2_MODEL_DIR", "")
    # inference_instruct2 takes a prompt clip: the clip sets who speaks, the instruction
    # sets how. Same reference set as the other engines, so voice identity stays constant
    # and the instruction alone carries the emotion.
    cosyvoice2_refs: str = os.getenv("ECHO_COSYVOICE2_REFS", "refs_ravdess_matched")
    # Parler-TTS: second mechanism-5 engine, so the mechanism claim is falsifiable
    parlertts_cmd: str = os.getenv(
        "ECHO_PARLERTTS_CMD",
        '{python} runners/parlertts_run.py --text "{text}" --out {out} '
        '--instruction "{instruction}" --seed {seed}')
    parlertts_python: str = os.getenv("ECHO_PARLERTTS_PYTHON", "")
    parlertts_repo: str = os.getenv("ECHO_PARLERTTS_REPO", "")
    parlertts_model_dir: str = os.getenv("ECHO_PARLERTTS_MODEL_DIR", "")
    # Seed for every stochastic engine; recorded per clip (T0.3).
    engine_seed: int = int(os.getenv("ECHO_ENGINE_SEED", "666"))

    # storage / output
    db_path: str = os.getenv("ECHO_DB", "echo.db")
    audio_dir: str = os.getenv("ECHO_AUDIO_DIR", "audio_out")

    # gate
    max_retries: int = int(os.getenv("ECHO_MAX_RETRIES", "2"))
    # G6: which EmotionJudge decides the emotion of a generated reply:
    # self-report (L0, legacy/leaky) | blind-llm (L1) | lexicon (L2) | cascade (default).
    # cascade = lexicon (L2, independent) with the blinded LLM (L1) as fallback when the
    # lexicon has no rated vocabulary for a reply. Measured 2026-08-30: the lexicon alone
    # abstains on ~12% of real replies even with the full Warriner norms, and an abstention
    # fails the gate and burns the retry budget.
    judge: str = os.getenv("ECHO_JUDGE", "cascade")
    # Warriner, Kuperman & Brysbaert (2013) norms, 13,915 lemmas, as published
    # (BRM-emot-submit.csv). If absent, the small built-in table is used, which is not
    # usable for a reported result; run check_norms.py to verify.
    affect_norms: str = os.getenv("ECHO_AFFECT_NORMS", "BRM-emot-submit.csv")

    # evaluation: audible-duration band. Clips outside [min, max] are flagged
    # (duration_ok=False), never silently altered, so the emotion signal stays intact.
    min_duration_s: float = float(os.getenv("ECHO_MIN_DURATION", "2.5"))
    max_duration_s: float = float(os.getenv("ECHO_MAX_DURATION", "15.0"))


def load_config() -> Config:
    return Config()
