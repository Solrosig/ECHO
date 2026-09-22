"""The site build — and the blinding assertions that make blinding a test rather than a habit.

On a static host there is no server to hide the token->condition mapping behind. The only place it
can be hidden is by not shipping it, so these tests check the *built output*: no engine name, no
condition label, no key file anywhere under the site folder.

Pataranutaporn et al. (2023, Nature Machine Intelligence) measured the effect this prevents:
participants interacting with the SAME system under different priming rated it more trustworthy,
more empathetic and better-performing, and the effect was stronger for more capable systems. An
engine name in the markup is a priming manipulation on exactly the constructs a listening test
collects.
"""

import csv
import json
import wave
from pathlib import Path

import build_test_site as b

ENGINE_NAMES = ("zipvoice", "chatterbox", "parlertts", "kokoro", "espeak", "sapi5xml")


def _wav(p: Path, frames=b"\x00\x01" * 400):
    p.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(p), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(22050)
        w.writeframes(frames)


def _register(tmp_path: Path) -> Path:
    """One clip per (condition, quadrant, stimulus) plus a practice session."""
    rows = []
    sessions = list(b.CONDITIONS) + [b.PRACTICE_SESSION]
    for session in sessions:
        engine = "zipvoice" if "zipvoice" in session else "kokoro"
        for q in b.QUADRANTS:
            for sid in ("S01", "S02", "S03"):
                wav = tmp_path / "audio" / f"{session}_{q}_{sid}.wav"
                _wav(wav)
                rows.append({
                    "session": session, "clip_id": f"{session}-{q}-{sid}", "engine": engine,
                    "quadrant": q, "stimulus_id": sid, "param_set": b.PARAM_SET,
                    "audio_path": str(wav),
                })
    reg = tmp_path / "register.csv"
    with open(reg, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    return reg


def _build(tmp_path, monkeypatch, stimuli=2):
    monkeypatch.chdir(tmp_path)          # the key is written to research/uat relative to cwd
    reg = _register(tmp_path)
    rows = b.load_register(reg)
    trials, practice = b.select(rows, stimuli)
    out = tmp_path / "site_out"
    key = b.write_site(out, trials, practice, Path(__file__).resolve().parents[1] / "site")
    return out, key, trials, practice


def test_no_engine_name_reaches_the_built_site(tmp_path, monkeypatch):
    """The assertion the whole blinding rests on: read the OUTPUT, not the templates."""
    out, _key, _t, _p = _build(tmp_path, monkeypatch)
    for f in out.rglob("*"):
        if f.is_file() and f.suffix in {".html", ".js", ".css", ".json"}:
            text = f.read_text(encoding="utf-8").lower()
            for name in ENGINE_NAMES:
                assert name not in text, f"{name} leaked into {f.name}"


def test_the_key_is_never_written_into_the_site(tmp_path, monkeypatch):
    """A static host cannot hide the mapping. Not shipping it is the only mechanism there is."""
    out, key, _t, _p = _build(tmp_path, monkeypatch)
    assert key.exists() and "research" in str(key)
    assert not list(out.rglob("*key*")), "a key file appeared inside the site folder"
    assert not list(out.rglob("*.csv")), "no CSV should ever be published with the site"


def test_manifest_carries_tokens_and_durations_only(tmp_path, monkeypatch):
    """Anything else in manifest.json is a side channel: it is fetched before the first trial."""
    out, _key, _t, _p = _build(tmp_path, monkeypatch)
    m = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    for group in ("test", "practice"):
        for entry in m[group]:
            assert set(entry) == {"token", "seconds"}, entry


def test_audio_filenames_are_opaque_and_stable(tmp_path, monkeypatch):
    """`zipvoice_b4_matched_S01_Q2.wav` in a network tab defeats the blinding on its own.
    Stability matters too: a rebuild must not rename every file and blow up the site diff."""
    out, _key, _t, _p = _build(tmp_path, monkeypatch)
    for wav in (out / "audio").glob("*.wav"):
        assert len(wav.stem) == 10 and wav.stem.isalnum()
    assert b.token_for("s", "c") == b.token_for("s", "c")


def test_selection_is_balanced_across_conditions_and_quadrants(tmp_path, monkeypatch):
    """An unbalanced set makes a condition x quadrant cell uninterpretable, and the imbalance is
    invisible once the order is shuffled in the browser."""
    _out, _key, trials, practice = _build(tmp_path, monkeypatch, stimuli=2)
    assert len(trials) == len(b.CONDITIONS) * len(b.QUADRANTS) * 2
    seen = {}
    for r in trials:
        seen[(r["session"], r["quadrant"])] = seen.get((r["session"], r["quadrant"]), 0) + 1
    assert set(seen.values()) == {2}
    assert len(practice) == len(b.QUADRANTS)


def test_practice_clips_come_from_outside_the_analysed_set(tmp_path, monkeypatch):
    """Otherwise the trials a listener spends learning the task contaminate a reported cell."""
    _out, _key, trials, practice = _build(tmp_path, monkeypatch)
    assert all(r["session"] == b.PRACTICE_SESSION for r in practice)
    assert all(r["session"] != b.PRACTICE_SESSION for r in trials)


def test_nojekyll_is_written(tmp_path, monkeypatch):
    """Without it GitHub Pages runs Jekyll and silently drops directories beginning with _."""
    out, _key, _t, _p = _build(tmp_path, monkeypatch)
    assert (out / ".nojekyll").exists()


def test_key_maps_every_published_clip_back_to_its_condition(tmp_path, monkeypatch):
    """The key is useless if it is incomplete: every token on the site must be resolvable."""
    out, key, _t, _p = _build(tmp_path, monkeypatch)
    tokens = {p.stem for p in (out / "audio").glob("*.wav")}
    keyed = {r["token"] for r in csv.DictReader(open(key, encoding="utf-8"))}
    assert tokens == keyed
