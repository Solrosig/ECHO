"""RAVDESS reference selection (Condition C). The quadrant->emotion mapping and the same-actor
constraint are what make the comparison valid, so both are pinned here. Uses tiny stub files —
the selection logic depends only on RAVDESS's filename convention, not on audio content."""

import make_ravdess_refs as mrr


def _ravdess_tree(tmp_path, actor=1, emotions=("02", "03", "04", "05"), intensity="02"):
    """Create stub files named per the RAVDESS convention:
    modality-vocalChannel-emotion-intensity-statement-repetition-actor.wav"""
    d = tmp_path / f"Actor_{actor:02d}"
    d.mkdir(parents=True, exist_ok=True)
    for emo in emotions:
        (d / f"03-01-{emo}-{intensity}-01-01-{actor:02d}.wav").write_bytes(b"RIFF")
    return tmp_path


def test_quadrant_mapping_matches_russell_axes():
    assert mrr.QUADRANT_EMOTION["Q1"][0] == "03"      # happy  -> v+ a+
    assert mrr.QUADRANT_EMOTION["Q2"][0] == "05"      # angry  -> v- a+
    assert mrr.QUADRANT_EMOTION["Q3"][0] == "04"      # sad    -> v- a-
    assert mrr.QUADRANT_EMOTION["Q4"][0] == "02"      # calm   -> v+ a-  (not 'neutral')


def test_builds_four_refs_from_one_actor(tmp_path, capsys):
    root = _ravdess_tree(tmp_path / "rav", actor=3)
    out = tmp_path / "refs_ravdess"
    assert mrr.main(["--ravdess", str(root), "--actor", "3", "--out", str(out)]) == 0
    assert sorted(p.name for p in out.glob("*.wav")) == ["Q1.wav", "Q2.wav", "Q3.wav", "Q4.wav"]
    printed = capsys.readouterr().out
    assert "Actor 03" in printed and "male" in printed          # odd actor = male


def test_same_actor_only(tmp_path):
    """Voice identity must be constant across quadrants: clips from another actor are ignored."""
    root = tmp_path / "rav"
    _ravdess_tree(root, actor=1, emotions=("03",))               # only 'happy' for actor 1
    _ravdess_tree(root, actor=2)                                 # all four for actor 2
    out = tmp_path / "refs"
    assert mrr.main(["--ravdess", str(root), "--actor", "1", "--out", str(out)]) == 1  # incomplete
    assert (out / "Q1.wav").exists() and not (out / "Q3.wav").exists()


def test_falls_back_when_exact_intensity_missing(tmp_path):
    """'calm'/'neutral' are not always recorded at strong intensity — selection must relax."""
    root = _ravdess_tree(tmp_path / "rav", actor=4, emotions=("02", "03", "04", "05"),
                         intensity="01")                          # only normal intensity exists
    out = tmp_path / "refs"
    assert mrr.main(["--ravdess", str(root), "--actor", "4", "--out", str(out),
                     "--intensity", "02"]) == 0                   # asked for strong, still found
    assert len(list(out.glob("*.wav"))) == 4
