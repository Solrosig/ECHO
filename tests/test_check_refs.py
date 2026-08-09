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
    _tone_wav(clipped, amp=1.0)                       # a sine at full scale -> sustained clipping
    assert any("clipped" in p for p in check_refs.check_clip(clipped)["problems"])

    quiet = tmp_path / "quiet.wav"
    _tone_wav(quiet, amp=0.02)
    assert any("too quiet" in p for p in check_refs.check_clip(quiet)["problems"])


def test_a_few_samples_at_full_scale_warn_but_do_not_fail(tmp_path):
    """3 samples touching the ceiling in a 5 s clip is inaudible and must NOT force a re-record;
    only a sustained proportion of pinned samples counts as clipping."""
    sr, seconds = 24000, 5.0
    t = np.arange(int(sr * seconds)) / sr
    x = 0.6 * np.sin(2 * math.pi * 150 * t)
    x[1000:1003] = 1.0                                # exactly 3 samples at full scale
    p = tmp_path / "edge.wav"
    with wave.open(str(p), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes((x * 32767).astype("<i2").tobytes())

    r = check_refs.check_clip(p)
    assert r["problems"] == []                        # usable
    assert any("full scale" in w for w in r["warnings"])


def test_quiet_low_arousal_clip_is_intentional_dynamics_not_a_fault(tmp_path):
    """A set of emotional references SHOULD have a wide dynamic range (RAVDESS: angry peaks 0.82,
    calm 0.02 = 35x). A quiet clip within a loud set is the arousal cue, not a recording fault."""
    quiet = tmp_path / "calm.wav"
    _tone_wav(quiet, amp=0.023)                       # like RAVDESS 'calm'
    r = check_refs.check_clip(quiet, set_peak=0.82)   # loudest clip in the set is 'angry'
    assert r["problems"] == []                        # usable
    assert any("intentional dynamics" in n for n in r.get("notes", []))


def test_uniformly_quiet_set_still_fails(tmp_path):
    """But if the whole set is quiet, that is a genuine gain problem and must fail."""
    quiet = tmp_path / "q.wav"
    _tone_wav(quiet, amp=0.05)
    r = check_refs.check_clip(quiet, set_peak=0.06)   # nothing in the set is loud
    assert any("whole set is too quiet" in p for p in r["problems"])


def test_silence_share_is_relative_to_peak(tmp_path):
    """A quiet but clean recording must not read as ~99% silence purely because its level is low."""
    p = tmp_path / "lowlevel.wav"
    _tone_wav(p, amp=0.02)                            # continuous tone, no silence at all
    r = check_refs.check_clip(p, set_peak=0.8)
    assert r["silence_share"] < 0.1                   # relative thresholding sees it as speech


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
