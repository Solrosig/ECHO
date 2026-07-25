"""Acoustic analyzer tests. Uses synthetic sine tones (known F0 and amplitude) so the
measurements are deterministic and checkable without real speech."""

import csv
import math
import wave

import numpy as np
import pytest

import analyze_acoustics as aa


def _sine_wav(path, f0, sr=22050, dur=1.0, amp=0.5):
    t = np.arange(int(sr * dur)) / sr
    samples = (amp * np.sin(2 * math.pi * f0 * t) * 32767).astype(np.int16)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(samples.tobytes())


def test_mean_f0_recovers_a_pure_tone(tmp_path):
    p = tmp_path / "tone.wav"
    _sine_wav(p, 200.0)
    x, sr = aa.read_wav(p)
    assert abs(aa.mean_f0(x, sr) - 200.0) / 200.0 < 0.05   # within 5 %


def test_f0_ordering_low_vs_high(tmp_path):
    lo, hi = tmp_path / "lo.wav", tmp_path / "hi.wav"
    _sine_wav(lo, 150.0)
    _sine_wav(hi, 300.0)
    xl, sr = aa.read_wav(lo)
    xh, _ = aa.read_wav(hi)
    assert aa.mean_f0(xl, sr) < aa.mean_f0(xh, sr)


def test_rms_dbfs_tracks_amplitude(tmp_path):
    soft, loud = tmp_path / "soft.wav", tmp_path / "loud.wav"
    _sine_wav(soft, 200.0, amp=0.2)
    _sine_wav(loud, 200.0, amp=0.9)
    xs, _ = aa.read_wav(soft)
    xl, _ = aa.read_wav(loud)
    assert aa.rms_dbfs(xl) > aa.rms_dbfs(xs)
    # a 0.5-amplitude sine has RMS = 0.5/sqrt(2) -> about -9 dBFS
    xm, _ = aa.read_wav(soft)  # reuse soft? no -- make a 0.5 tone
    m = tmp_path / "mid.wav"
    _sine_wav(m, 200.0, amp=0.5)
    xm, _ = aa.read_wav(m)
    assert abs(aa.rms_dbfs(xm) - (-9.0)) < 1.0


def test_analyze_clip_reports_all_fields(tmp_path):
    p = tmp_path / "clip.wav"
    _sine_wav(p, 220.0, dur=2.0)
    a = aa.analyze_clip(p, text="one two three four five six")
    assert a["f0_hz"] > 0 and a["silent"] == "no"
    assert a["words_per_s"] > 0
    assert abs(a["measured_dur_s"] - 2.0) < 0.05


def test_f0_variability_stats(tmp_path):
    # a steady tone has near-zero F0 spread
    steady = tmp_path / "steady.wav"
    _sine_wav(steady, 200.0, dur=1.0)
    xs, sr = aa.read_wav(steady)
    s = aa.f0_stats(xs, sr)
    assert s["f0_sd_hz"] < 3.0 and s["f0_range_hz"] < 6.0
    # a stepped tone (150 Hz -> 300 Hz) has clear F0 variability
    sr2 = 22050
    t = np.arange(sr2) / sr2
    seg = np.concatenate([0.5 * np.sin(2 * math.pi * 150 * t), 0.5 * np.sin(2 * math.pi * 300 * t)])
    stepped = tmp_path / "stepped.wav"
    with wave.open(str(stepped), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr2)
        w.writeframes((seg * 32767).astype(np.int16).tobytes())
    xv, srv = aa.read_wav(stepped)
    sv = aa.f0_stats(xv, srv)
    assert sv["f0_sd_hz"] > 20.0
    assert sv["f0_range_hz"] > 100.0


def test_analyze_clip_includes_f0_variability(tmp_path):
    p = tmp_path / "clip2.wav"
    _sine_wav(p, 220.0, dur=1.5)
    a = aa.analyze_clip(p, text="one two three")
    assert "f0_sd_hz" in a and "f0_range_hz" in a


def test_praat_backend_on_tone(tmp_path):
    pytest.importorskip("parselmouth")
    p = tmp_path / "praat_tone.wav"
    _sine_wav(p, 200.0, dur=1.5)
    a = aa.analyze_clip(p, text="one two three four")
    assert a["backend"] == "praat"
    assert abs(a["f0_hz"] - 200.0) / 200.0 < 0.05          # Praat recovers the tone
    assert a["hnr"] != "" and float(a["hnr"]) > 15.0       # a clean tone -> high HNR
    assert a["jitter"] != "" and a["shimmer"] != ""        # voice-quality columns present


def test_numpy_fallback_when_praat_unavailable(tmp_path, monkeypatch):
    monkeypatch.setattr(aa, "_HAVE_PRAAT", False)
    p = tmp_path / "fallback_tone.wav"
    _sine_wav(p, 200.0, dur=1.0)
    a = aa.analyze_clip(p, text="a b c")
    assert a["backend"] == "numpy"
    assert a["f0_hz"] > 0                                   # numpy still measures F0
    assert a["jitter"] == "" and a["shimmer"] == "" and a["hnr"] == ""  # no VQ on fallback


def test_silent_clip_is_flagged(tmp_path):
    p = tmp_path / "quiet.wav"
    _sine_wav(p, 200.0, amp=0.0)          # all zeros
    a = aa.analyze_clip(p, text="hello world")
    assert a["silent"] == "yes"
    assert a["f0_hz"] == 0.0


def test_cli_writes_acoustics_and_returns_zero(tmp_path):
    neutral = tmp_path / "neutral_Q1.wav"
    full = tmp_path / "full_Q1.wav"
    _sine_wav(neutral, 180.0)
    _sine_wav(full, 260.0)               # "full" rendered higher-pitched than neutral
    reg = tmp_path / "register.csv"
    with open(reg, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["audio_path", "text", "param_set", "quadrant"])
        w.writeheader()
        w.writerow({"audio_path": str(neutral), "text": "a b c d", "param_set": "neutral", "quadrant": "Q1"})
        w.writerow({"audio_path": str(full), "text": "a b c d", "param_set": "rate_volume_pitch", "quadrant": "Q1"})
    out = tmp_path / "acoustics.csv"
    assert aa.main(["--register", str(reg), "--out", str(out)]) == 0
    assert out.exists()
    rows = list(csv.DictReader(open(out, encoding="utf-8")))
    assert len(rows) == 2
    assert all("f0_hz" in r and "rms_dbfs" in r for r in rows)
    # E5.1/E5.2/E5.3 columns are surfaced in the written register
    assert all(c in rows[0] for c in ("f0_sd_hz", "f0_range_hz", "jitter", "shimmer", "hnr", "backend"))
