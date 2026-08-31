"""check_zipvoice.py — the executable T0.3 gate.

The point of the script is its VERDICT logic, so that is what is tested: which hash pattern
fails, which passes, and which is merely reported. The engine is never invoked — `render` is
substituted, so the whole decision table runs offline in milliseconds.

The distinction under test is the one it would be easy to get wrong: "different seeds give
identical audio" is NOT a failure. It means the configuration is deterministic regardless of
the seed, which is stronger than the filter requires. Failing it would repeat the mistake
check_refs.py made when it failed the RAVDESS set for having emotional dynamics.
"""

import wave

import check_zipvoice as cz


def _wav(path, seconds=1.0, sr=24000):
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(b"\x00\x00" * int(sr * seconds))
    return path


def _refs(tmp_path, quadrant="Q1"):
    d = tmp_path / "refs"
    d.mkdir(parents=True, exist_ok=True)
    _wav(d / f"{quadrant}.wav")
    (d / f"{quadrant}.txt").write_text("Kids are talking by the door.", encoding="utf-8")
    return d


def _run(tmp_path, monkeypatch, contents):
    """Run main() with `render` replaced by a stub that writes the given bytes in order."""
    seq = list(contents)

    def fake_render(adapter, text, quadrant, out_path):
        payload = seq.pop(0)
        _wav(out_path)                                   # a real, readable WAV header
        with open(out_path, "ab") as fh:                 # ...plus a distinguishing payload
            fh.write(payload)
        return out_path, 0.5

    monkeypatch.setattr(cz, "render", fake_render)
    return cz.main(["--refs", str(_refs(tmp_path)), "--out", str(tmp_path / "out"),
                    "--python", "x", "--seed", "42"])


# --- the verdict table -----------------------------------------------------

def test_same_seed_reproducing_passes(tmp_path, monkeypatch, capsys):
    """A == B, A != C: the intended case — the seed pins the sampling."""
    assert _run(tmp_path, monkeypatch, [b"same", b"same", b"other"]) == 0
    out = capsys.readouterr().out
    assert "byte-for-byte" in out
    assert "VERDICT" in out


def test_same_seed_diverging_fails(tmp_path, monkeypatch, capsys):
    """A != B is the only real failure: identical inputs, different audio, so the
    provenance hash records a one-off artefact."""
    assert _run(tmp_path, monkeypatch, [b"one", b"two", b"three"]) == 1
    assert "DIFFERENT audio" in capsys.readouterr().out


def test_seed_independence_is_reported_not_failed(tmp_path, monkeypatch, capsys):
    """A == B == C: deterministic whatever the seed. STRONGER than required, so it must
    pass — failing it would penalise an engine for exceeding the criterion."""
    assert _run(tmp_path, monkeypatch, [b"x", b"x", b"x"]) == 0
    out = capsys.readouterr().out
    assert "deterministic regardless of the seed" in out
    assert "FAIL" not in out


# --- preconditions ---------------------------------------------------------

def test_missing_reference_clip_names_the_fix(tmp_path, capsys):
    assert cz.main(["--refs", str(tmp_path / "nothing"), "--out", str(tmp_path / "o")]) == 1
    assert "make_ravdess_refs.py" in capsys.readouterr().out


def test_missing_transcript_is_its_own_failure(tmp_path, capsys):
    """A clip without a transcript is unusable to a zero-shot engine, and the message must
    say so rather than reporting a generic missing-reference error."""
    d = tmp_path / "refs"
    d.mkdir()
    _wav(d / "Q1.wav")                                   # transcript deliberately absent
    assert cz.main(["--refs", str(d), "--out", str(tmp_path / "o")]) == 1
    assert "transcript" in capsys.readouterr().out


def test_render_failure_is_reported_with_the_engine_message(tmp_path, monkeypatch, capsys):
    def boom(*a, **k):
        raise RuntimeError("ZipVoice failed (exit 1):\n  ModuleNotFoundError: zipvoice")

    monkeypatch.setattr(cz, "render", boom)
    assert cz.main(["--refs", str(_refs(tmp_path)), "--out", str(tmp_path / "o"),
                    "--python", "x"]) == 1
    assert "ModuleNotFoundError" in capsys.readouterr().out


def test_unreadable_output_fails(tmp_path, monkeypatch, capsys):
    """A non-WAV file must fail here rather than reaching the analysis scripts."""
    def junk(adapter, text, quadrant, out_path):
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(b"not a wav")
        return out_path, 0.1

    monkeypatch.setattr(cz, "render", junk)
    assert cz.main(["--refs", str(_refs(tmp_path)), "--out", str(tmp_path / "o"),
                    "--python", "x"]) == 1
    assert "not a valid WAV" in capsys.readouterr().out.replace("UNREADABLE — ", "")


# --- probe clips are evidence, not scratch ---------------------------------

def test_probe_clips_are_kept_and_timestamped(tmp_path, monkeypatch):
    """Standing rule: never overwrite a run. Two checks must leave two sets of clips."""
    out = tmp_path / "out"
    _run(tmp_path, monkeypatch, [b"a", b"a", b"b"])
    first = sorted(p.name for p in out.glob("*.wav"))
    assert len(first) == 3
    assert all("_seed" in n for n in first)


def test_every_setting_reaches_the_adapter(tmp_path, monkeypatch):
    """Regression guard for a real failure (2026-08-30).

    `repo` was added to ZipVoiceAdapter and to make_tts but NOT to this script's adapter
    construction, so the check ran with no PYTHONPATH and reported `No module named
    'zipvoice'` for a package that was present — a confusing failure caused entirely by a
    settings mapping that exists in two places. This pins the mapping.
    """
    seen = {}

    class Spy:
        def __init__(self, **kw):
            seen.update(kw)

        def synthesize(self, text, vp, out_path):
            _wav(out_path)
            return out_path

    monkeypatch.setattr(cz, "ZipVoiceAdapter", Spy)
    cz.main(["--refs", str(_refs(tmp_path)), "--out", str(tmp_path / "o"),
             "--python", "PY", "--repo", "REPO", "--model", "zipvoice_distill",
             "--seed", "7"])
    assert seen["repo"] == "REPO"            # the setting that was missed
    assert seen["python"] == "PY"
    assert seen["model_name"] == "zipvoice_distill"
    assert "num_thread" in seen and "target_rms" in seen and "num_step" in seen


def test_helpers(tmp_path):
    p = _wav(tmp_path / "a.wav", seconds=0.5, sr=24000)
    assert cz.sha256_of(p) == cz.sha256_of(p)
    duration, sr = cz.wav_info(p)
    assert sr == 24000 and 0.4 < duration < 0.6
    assert cz.wav_info(tmp_path / "missing.wav") is None
