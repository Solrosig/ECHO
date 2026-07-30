"""Reference-clip validator (Condition B pre-flight). A bad reference silently degrades every
synthesised clip and a render costs ~20 minutes, so the checks must actually catch the common
recording faults: missing, too short, clipped, too quiet."""

import math
import wave

import numpy as np

import check_refs


def _tone_wav(path, seconds=6.0, sr=24000, amp=0.5, channels=1):
    t = np.arange(int(sr * seconds)) / sr
    x = amp * np.sin(2 * math.pi * 150 * t)
    data = (x * 32767).astype("<i2")
    if channels == 2:
        data = np.repeat(data, 2)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(data.tobytes())


def test_good_clip_passes(tmp_path):
    p = tmp_path / "Q1.wav"
    _tone_wav(p)
    r = check_refs.check_clip(p)
    assert r["problems"] == []
    assert r["seconds"] == 6.0 and r["sr"] == 24000 and r["channels"] == 1


def test_missing_and_short_and_clipped_and_quiet_are_caught(tmp_path):
    assert "missing" in check_refs.check_clip(tmp_path / "nope.wav")["problems"]

    short = tmp_path / "short.wav"
    _tone_wav(short, seconds=1.0)
    assert any("too short" in p for p in check_refs.check_clip(short)["problems"])

    clipped = tmp_path / "clip.wav"
    _tone_wav(clipped, amp=1.0)
    assert any("clipped" in p for p in check_refs.check_clip(clipped)["problems"])

    quiet = tmp_path / "quiet.wav"
    _tone_wav(quiet, amp=0.02)
    assert any("too quiet" in p for p in check_refs.check_clip(quiet)["problems"])


def test_stereo_warns_but_does_not_fail(tmp_path):
    p = tmp_path / "stereo.wav"
    _tone_wav(p, channels=2)
    r = check_refs.check_clip(p)
    assert r["problems"] == [] and any("channels" in w for w in r["warnings"])


def test_cli_returns_nonzero_until_all_four_exist(tmp_path, capsys):
    _tone_wav(tmp_path / "Q1.wav")
    assert check_refs.main(["--dir", str(tmp_path)]) == 1        # Q2..Q4 still missing
    for q in ("Q2", "Q3", "Q4"):
        _tone_wav(tmp_path / f"{q}.wav")
    assert check_refs.main(["--dir", str(tmp_path)]) == 0
    assert "All four references usable" in capsys.readouterr().out
