"""Instrument ceilings (M1/M2) — the analysis that decides what ECHO's valence result means.

The recogniser and UTMOS are never loaded here. What is tested is the sampling and the
reporting, because those are what make the ceiling comparable to ECHO's own numbers: a
sample concentrated in a few RAVDESS actors would measure those actors rather than the
instrument, and a mapping applied silently would repeat the categorical->dimensional
assumption the project's own protocol requires to be declared.
"""

from pathlib import Path

import check_instruments as ci


def _tree(tmp_path, actors=(1, 2, 3, 4), emotions=("03", "05", "04", "02"), reps=("01", "02")):
    root = tmp_path / "RAVDESS"
    for a in actors:
        d = root / f"Actor_{a:02d}"
        d.mkdir(parents=True, exist_ok=True)
        for e in emotions:
            for r in reps:
                (d / f"03-01-{e}-02-01-{r}-{a:02d}.wav").write_bytes(b"RIFF")
    return root


# --- filename decoding -----------------------------------------------------

def test_filename_decodes_to_the_declared_quadrant():
    c = ci.parse_ravdess(Path("03-01-03-02-01-01-07.wav"))
    assert c["quadrant"] == "Q1" and c["label"] == "happy" and c["actor"] == 7


def test_unmapped_emotions_are_excluded():
    """RAVDESS has eight emotions; only the four with a declared quadrant are usable.
    Including 'fearful' or 'surprised' would require a mapping nobody has justified."""
    assert ci.parse_ravdess(Path("03-01-06-02-01-01-01.wav")) is None   # fearful
    assert ci.parse_ravdess(Path("03-01-08-02-01-01-01.wav")) is None   # surprised
    assert ci.parse_ravdess(Path("03-01-01-02-01-01-01.wav")) is None   # neutral


def test_non_speech_modalities_are_excluded():
    assert ci.parse_ravdess(Path("01-01-03-02-01-01-01.wav")) is None   # video-only
    assert ci.parse_ravdess(Path("03-02-03-02-01-01-01.wav")) is None   # song
    assert ci.parse_ravdess(Path("not-a-ravdess-name.wav")) is None


def test_mapping_matches_the_reference_builder():
    """The ceiling must be measured under the SAME assumption the reference clips use, or
    it is not a ceiling for this project."""
    from make_ravdess_refs import QUADRANT_EMOTION

    assert ci.EMOTION_QUADRANT == {c: q for q, (c, _) in QUADRANT_EMOTION.items()}


# --- sampling --------------------------------------------------------------

def test_sample_is_balanced_across_quadrants(tmp_path):
    clips = ci.sample_balanced(_tree(tmp_path), per_quadrant=4, seed=1)
    from collections import Counter

    assert Counter(c["quadrant"] for c in clips) == {"Q1": 4, "Q2": 4, "Q3": 4, "Q4": 4}


def test_sample_spreads_across_actors(tmp_path):
    """A recogniser's apparent accuracy can be carried by a few expressive performers, so
    a sample concentrated in one actor would measure the actor, not the instrument."""
    clips = ci.sample_balanced(_tree(tmp_path), per_quadrant=4, seed=1)
    for q in ("Q1", "Q2", "Q3", "Q4"):
        actors = {c["actor"] for c in clips if c["quadrant"] == q}
        assert len(actors) == 4          # one per available actor, not four from one


def test_sampling_is_deterministic_under_the_seed(tmp_path):
    root = _tree(tmp_path)
    a = [c["path"].name for c in ci.sample_balanced(root, 3, seed=42)]
    b = [c["path"].name for c in ci.sample_balanced(root, 3, seed=42)]
    assert a == b


def test_sampling_does_not_exceed_the_pool(tmp_path):
    clips = ci.sample_balanced(_tree(tmp_path, actors=(1,), reps=("01",)), per_quadrant=99, seed=1)
    assert len(clips) == 4               # one clip per quadrant exists; asking for 99 is fine


# --- reporting -------------------------------------------------------------

def test_confusion_rows_are_targets_and_diagonal_is_accuracy():
    pairs = [("Q1", "Q1"), ("Q1", "Q2"), ("Q2", "Q2"), ("Q2", "Q2")]
    out = ci.confusion(pairs)
    assert "Q1" in out and "50%" in out and "100%" in out


def test_confusion_handles_an_empty_target_row():
    """A quadrant the recogniser never sees must print as 0 %, not divide by zero."""
    assert "0%" in ci.confusion([("Q1", "Q1")])


def test_mean_ci_degrades_rather_than_raising():
    import math

    m, lo, hi = ci.mean_ci([1.0, 2.0, 3.0])
    assert m == 2.0 and lo < m < hi
    assert math.isnan(ci.mean_ci([])[0])
    assert math.isnan(ci.mean_ci([4.5])[1])          # single value: no interval, no crash


def test_missing_ravdess_folder_names_the_fix(tmp_path, capsys):
    assert ci.main(["--ravdess", str(tmp_path / "nope"), "--skip-utmos"]) == 1
    assert "Audio_Speech_Actors" in capsys.readouterr().out


# --- M2 anchor pool: neutral, not emotional (corrected 2026-08-31) ---------

def test_neutral_clips_parse_only_when_allowed():
    """Neutral has no quadrant, so M1 must exclude it — but M2 requires it."""
    p = Path("03-01-01-01-01-01-05.wav")
    assert ci.parse_ravdess(p) is None                       # M1: excluded
    c = ci.parse_ravdess(p, allow_neutral=True)              # M2: admitted
    assert c["label"] == "neutral" and c["quadrant"] == ""


def test_anchor_pool_is_neutral_only(tmp_path):
    """The first run scored UTMOS over EMOTIONAL speech and reported 3.353 as the 'natural
    anchor' — below five of seven engine configurations, which would have invalidated the
    naturalness scale. Naturalness is not emotion."""
    root = tmp_path / "R"
    for a in (1, 2, 3):
        d = root / f"Actor_{a:02d}"
        d.mkdir(parents=True)
        for e in ("01", "03", "05"):                          # neutral, happy, angry
            (d / f"03-01-{e}-01-01-01-{a:02d}.wav").write_bytes(b"RIFF")
    pool = ci.natural_anchor_pool(root, n=3, seed=1)
    assert len(pool) == 3
    assert all(c["emotion"] == ci.NEUTRAL_CODE for c in pool)
    assert len({c["actor"] for c in pool}) == 3               # spread across actors


def test_anchor_pool_is_deterministic_and_bounded(tmp_path):
    root = tmp_path / "R"
    d = root / "Actor_01"
    d.mkdir(parents=True)
    (d / "03-01-01-01-01-01-01.wav").write_bytes(b"RIFF")
    assert len(ci.natural_anchor_pool(root, n=50, seed=1)) == 1     # cannot exceed the pool
    a = [c["path"].name for c in ci.natural_anchor_pool(root, 1, seed=7)]
    b = [c["path"].name for c in ci.natural_anchor_pool(root, 1, seed=7)]
    assert a == b
