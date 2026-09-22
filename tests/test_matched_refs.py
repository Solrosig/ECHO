"""Level-matched references, and the guard against silently-destroyed prompts (Story B4.5).

Both exist because of a measured failure on 2026-08-31: ZipVoice strips its prompt with a
pydub gate at an ABSOLUTE -50 dBFS, before any normalisation. The RAVDESS Q4 'calm'
reference sits near -52 dBFS RMS — because low arousal IS quiet — so the engine deleted it
and emitted 0.10-0.21 s for all five Q4 stimuli, in both rendered conditions. The register
recorded that only as `duration_ok=no`.

These tests pin the two things that must not regress: the guard refuses such a reference and
says why, and the matching lifts every clip above the gate without touching within-clip
dynamics.
"""

import numpy as np
import pytest

import tts

sf = pytest.importorskip("soundfile")
import make_matched_refs as mmr  # noqa: E402  (after the soundfile skip)


#: Levels measured from the real RAVDESS reference set on 2026-08-31, as RMS amplitude.
#: Scaling by RMS rather than by peak matters: real speech has a crest factor near 9
#: (Q4 peak 0.0227 against RMS 0.0024), where a synthetic tone has one near 2 — so a
#: fixture built to a peak is nowhere near as quiet as the clip it is standing in for.
OBSERVED_RMS = {"Q1": 0.01103, "Q2": 0.08897, "Q3": 0.00473, "Q4": 0.00241}


#: Syllable levels spanning roughly 18 dB, which is what gives the fixture a crest factor
#: near 6 — close enough to speech that a low-RMS clip has most of its 10 ms chunks under
#: the gate. An earlier fixture used a constant-amplitude tone (crest ~2) and reported the
#: quiet clip as 61 % surviving, which is the opposite of what the real file does.
_SYLLABLES = (1.0, 0.45, 0.18, 0.75, 0.30, 0.12, 0.60, 0.22)


def _speech_like(path, rms=None, peak=None, seconds=2.0, sr=24000):
    """A clip with speech-like structure, scaled to a target RMS or a target peak."""
    x = np.zeros(int(sr * seconds), dtype="float64")
    for i, level in enumerate(_SYLLABLES):
        start, end = int((0.10 + i * 0.24) * sr), int((0.10 + i * 0.24 + 0.12) * sr)
        if end > len(x):
            break
        span = np.arange(end - start) / sr
        envelope = np.sin(np.pi * np.linspace(0, 1, end - start)) ** 2
        x[start:end] = np.sin(2 * np.pi * 140 * span) * envelope * level
    if rms is not None:
        x = x / max(float(np.sqrt((x ** 2).mean())), 1e-12) * rms
    else:
        x = x / max(float(np.abs(x).max()), 1e-12) * peak
    sf.write(str(path), x.astype("float32"), sr, subtype="PCM_16")
    return x, sr


def _refs(dirpath, levels, by="rms"):
    dirpath.mkdir(parents=True, exist_ok=True)
    for q, v in levels.items():
        _speech_like(dirpath / f"{q}.wav", **{by: v})
        (dirpath / f"{q}.txt").write_text("Kids are talking by the door.", encoding="utf-8")
    return dirpath


# --- the guard --------------------------------------------------------------

def test_quiet_reference_is_refused_with_the_cause_and_the_fix(tmp_path):
    """A 0.1 s clip is not a bad synthesis result, it is an absent one — it must not reach
    the corpus wearing the same row shape as a real measurement."""
    refs = _refs(tmp_path / "refs", {"Q4": OBSERVED_RMS["Q4"]})   # the real calm level
    a = tts.ZipVoiceAdapter(refs_dir=str(refs))
    with pytest.raises(RuntimeError) as exc:
        a.synthesize("hello", _vp(quadrant="Q4"), tmp_path / "o.wav")
    msg = str(exc.value)
    assert "silence gate" in msg
    assert "make_matched_refs.py" in msg               # names the fix
    assert "TARGET_RMS=0 does not help" in msg         # forecloses the wrong fix


def test_normal_reference_passes_the_guard(tmp_path):
    refs = _refs(tmp_path / "refs", {"Q2": OBSERVED_RMS["Q2"]})
    a = tts.ZipVoiceAdapter(refs_dir=str(refs))
    a._assert_reference_is_audible(str(refs / "Q2.wav"), "Q2")   # must not raise


def test_guard_never_blocks_when_it_cannot_measure(tmp_path):
    """A guard that fails closed on an unreadable file would block renders for a reason
    unrelated to the audio."""
    refs = _refs(tmp_path / "refs", {"Q1": OBSERVED_RMS["Q1"]})
    (refs / "Q1.wav").write_bytes(b"not audio")
    tts.ZipVoiceAdapter(refs_dir=str(refs))._assert_reference_is_audible(
        str(refs / "Q1.wav"), "Q1")                    # must not raise


def _vp(**kw):
    from strategies import VoiceParams

    base = dict(voice_id="v", rate=1.0, volume=1.0, pitch=1.0, quadrant="Q1")
    base.update(kw)
    return VoiceParams(**base)


# --- surviving-fraction estimate -------------------------------------------

def test_surviving_fraction_separates_the_observed_cases(tmp_path):
    """Mirrors pydub's chunk scan rather than judging by overall RMS, which would
    misestimate a clip whose energy is unevenly distributed."""
    q4, sr = _speech_like(tmp_path / "q4.wav", rms=OBSERVED_RMS["Q4"])   # was destroyed
    q3, _ = _speech_like(tmp_path / "q3.wav", rms=OBSERVED_RMS["Q3"])    # rendered fine
    q2, _ = _speech_like(tmp_path / "q2.wav", rms=OBSERVED_RMS["Q2"])    # rendered fine
    # The estimate must reproduce the ACTUAL outcome: Q4 below the guard, Q3 — the next
    # quietest, and the one that rendered at 6.75-8.67 s — above it. If the two landed on
    # the same side, the threshold would be separating nothing.
    assert mmr.surviving_fraction(q4, sr) < tts.ZipVoiceAdapter.MIN_SURVIVING_FRACTION
    assert mmr.surviving_fraction(q3, sr) > tts.ZipVoiceAdapter.MIN_SURVIVING_FRACTION
    assert mmr.surviving_fraction(q2, sr) > mmr.surviving_fraction(q3, sr)


def test_dbfs_handles_silence_without_infinity():
    assert mmr.dbfs(1.0) == pytest.approx(0.0)
    assert mmr.dbfs(0.0) == -120.0                      # not -inf, so tables stay printable


# --- matching ---------------------------------------------------------------

def test_matching_lifts_every_clip_above_the_gate(tmp_path):
    src = _refs(tmp_path / "src", OBSERVED_RMS)
    out = tmp_path / "matched"
    assert mmr.main(["--refs", str(src), "--out", str(out)]) == 0
    for q in ("Q1", "Q2", "Q3", "Q4"):
        x, sr = sf.read(str(out / f"{q}.wav"), dtype="float32")
        assert np.abs(x).max() == pytest.approx(0.8, abs=0.02)     # common peak
        assert mmr.surviving_fraction(x, sr) > 0.2                 # clears the gate
        assert (out / f"{q}.txt").exists()                         # transcript carried over


def test_matching_preserves_within_clip_dynamics(tmp_path):
    """The manipulation removes the BETWEEN-quadrant loudness difference only. If it also
    flattened within-clip dynamics it would be destroying prosody, not levelling gain."""
    src = _refs(tmp_path / "src", {"Q4": OBSERVED_RMS["Q4"]})
    out = tmp_path / "matched"
    mmr.main(["--refs", str(src), "--out", str(out)])
    a, _ = sf.read(str(src / "Q4.wav"), dtype="float64")
    b, _ = sf.read(str(out / "Q4.wav"), dtype="float64")
    # a pure gain change leaves the waveform's shape — hence its correlation — intact
    assert np.corrcoef(a, b)[0, 1] > 0.999


def test_source_set_is_never_modified(tmp_path):
    """Standing rule: inputs and results move forward, they are not edited in place."""
    src = _refs(tmp_path / "src", {"Q4": OBSERVED_RMS["Q4"]})
    before = (src / "Q4.wav").read_bytes()
    mmr.main(["--refs", str(src), "--out", str(tmp_path / "matched")])
    assert (src / "Q4.wav").read_bytes() == before


def test_missing_transcript_is_reported(tmp_path, capsys):
    src = _refs(tmp_path / "src", {"Q1": OBSERVED_RMS["Q1"]})
    (src / "Q1.txt").unlink()
    assert mmr.main(["--refs", str(src), "--out", str(tmp_path / "m")]) == 1
    assert "no transcript" in capsys.readouterr().out
