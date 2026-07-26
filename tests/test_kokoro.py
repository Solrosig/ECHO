"""Kokoro adapter (Story N3). The adapter is lazy — constructing it must NOT require the
package or model files; those are only needed at synthesis time. Real synthesis runs only
if kokoro-onnx and the model files are both present."""

import os
import wave

import pytest

import tts
from config import load_config
from strategies import VoiceParams


def test_make_tts_kokoro_is_lazy_and_registered():
    a = tts.make_tts("kokoro", kokoro_model="nope.onnx", kokoro_voices="nope.bin")
    assert a.engine_id == "kokoro" and a.natural is True   # constructed without loading a model


def test_synthesize_without_model_raises_clear_error(tmp_path):
    a = tts.make_tts("kokoro", kokoro_model=str(tmp_path / "missing.onnx"),
                     kokoro_voices=str(tmp_path / "missing.bin"))
    vp = VoiceParams(voice_id="af_heart", rate=1.0, volume=1.0, pitch=1.0)
    with pytest.raises(RuntimeError):
        a.synthesize("hello", vp, tmp_path / "o.wav")


def _kokoro_ready() -> bool:
    try:
        import kokoro_onnx  # noqa: F401
    except Exception:
        return False
    cfg = load_config()
    return os.path.exists(cfg.kokoro_model_path) and os.path.exists(cfg.kokoro_voices_path)


@pytest.mark.skipif(not _kokoro_ready(), reason="kokoro-onnx or model files not available")
def test_real_kokoro_synthesis_writes_wav(tmp_path):
    cfg = load_config()
    a = tts.make_tts("kokoro", kokoro_model=cfg.kokoro_model_path, kokoro_voices=cfg.kokoro_voices_path)
    vp = VoiceParams(voice_id=cfg.kokoro_voice, rate=1.05, volume=0.9, pitch=1.0)
    out = a.synthesize("hello world", vp, tmp_path / "k.wav")
    assert out.exists()
    with wave.open(str(out), "rb") as w:
        assert w.getnframes() > 0
