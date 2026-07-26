"""eSpeak NG adapter (Story N2). Parameter mapping and registration are tested without
the binary; a real-synthesis test runs only if the espeak-ng binary is installed."""

import shutil
import wave

import pytest

import tts
from strategies import VoiceParams

_HAVE_ESPEAK = bool(shutil.which("espeak-ng") or shutil.which("espeak"))


def test_param_mapping_is_monotonic_and_calibrated():
    assert tts._espeak_speed(1.0) == 175
    assert tts._espeak_speed(1.3) > tts._espeak_speed(0.7)          # faster with rate
    assert tts._espeak_pitch(1.0) == 50
    assert tts._espeak_pitch(1.2) == 70 and tts._espeak_pitch(0.8) == 30   # real pitch range
    assert tts._espeak_amp(1.0) == 150 and tts._espeak_amp(0.6) < tts._espeak_amp(1.0)


def test_make_tts_and_matrix_include_espeak():
    assert tts.make_tts("espeak", kokoro_model="x", kokoro_voices="y").engine_id == "espeak"
    m = {r["engine"]: r for r in tts.capability_matrix()}
    assert m["espeak"]["rate"] == "yes" and m["espeak"]["volume"] == "yes" and m["espeak"]["pitch"] == "yes"


def test_missing_binary_raises_clear_error(monkeypatch, tmp_path):
    monkeypatch.setattr(tts, "_find_espeak", lambda: None)     # force "not found"
    vp = VoiceParams(voice_id="v", rate=1.0, volume=1.0, pitch=1.0)
    with pytest.raises(RuntimeError):
        tts.EspeakNgAdapter().synthesize("hi", vp, tmp_path / "o.wav")


def test_find_espeak_honors_env_override(tmp_path, monkeypatch):
    fake = tmp_path / "espeak-ng"
    fake.write_text("")                                        # any existing file
    monkeypatch.setenv("ECHO_ESPEAK_BIN", str(fake))
    assert tts._find_espeak() == str(fake)


@pytest.mark.skipif(not _HAVE_ESPEAK, reason="espeak-ng binary not installed")
def test_real_synthesis_writes_wav(tmp_path):
    vp = VoiceParams(voice_id="v", rate=1.1, volume=0.9, pitch=1.15)
    out = tts.EspeakNgAdapter().synthesize("hello world", vp, tmp_path / "e.wav")
    assert out.exists()
    with wave.open(str(out), "rb") as w:
        assert w.getnframes() > 0
