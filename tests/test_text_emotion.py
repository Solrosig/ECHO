"""Layer 1 — text-side emotion classification (story C1).

The heavy classifier is never loaded here: what matters for the research claim is that
the label->quadrant map comes from PUBLISHED NORMS rather than assumption, that `neutral`
is not silently turned into a Q4 prediction, and that results are never overwritten.
"""

import pytest

import text_emotion as te
from contracts import Quadrant


def test_labels_are_positioned_from_the_norms_not_by_assertion():
    """The 'map' step of the categorical->dimensional protocol."""
    norms = {"anger": (2.5, 7.2), "joy": (8.2, 6.6), "sadness": (2.1, 3.5),
             "fear": (2.8, 6.9), "disgust": (2.4, 5.5), "surprise": (7.0, 7.4)}
    positions, grounded = te.label_positions(norms)
    assert grounded is True
    assert positions["anger"][2] is Quadrant.Q2      # negative valence, high arousal
    assert positions["joy"][2] is Quadrant.Q1        # positive, high
    assert positions["sadness"][2] is Quadrant.Q3    # negative, low


def test_missing_labels_fall_back_and_the_run_is_flagged_as_not_citable():
    positions, grounded = te.label_positions({})
    assert grounded is False                          # caller must warn
    assert positions["anger"][2] is Quadrant.Q2       # still usable


def test_neutral_is_not_a_quadrant():
    """'No emotion detected' is not the same claim as 'calm'. Collapsing them would turn
    an abstention into a Q4 prediction and inflate Q4 accuracy."""
    positions, _ = te.label_positions({})
    assert positions["neutral"] is None


def test_rescale_maps_the_rating_scale_onto_the_contract_axes():
    assert te._rescale(5.0) == 0.0
    assert te._rescale(9.0) == 1.0
    assert te._rescale(1.0) == -1.0
    assert -1.0 <= te._rescale(99.0) <= 1.0           # clamped


def test_reads_only_replies_that_exist(tmp_path):
    import sqlite3
    db = tmp_path / "t.db"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE turns (turn_uuid TEXT, ts TEXT, quadrant TEXT, "
                 "reply TEXT, prompt_version TEXT)")
    conn.executemany("INSERT INTO turns VALUES (?,?,?,?,?)", [
        ("a", "2026-01-01", "Q1", "lovely news", "prompts-v2"),
        ("b", "2026-01-02", "Q2", "", "prompts-v2"),          # empty -> excluded
        ("c", "2026-01-03", "Q3", "   ", "prompts-v2"),       # blank -> excluded
        ("d", "2026-01-04", "Q4", "all calm", "prompts-v1"),  # other version
    ])
    conn.commit()
    conn.close()

    assert [r["turn_uuid"] for r in te.read_replies(str(db))] == ["a", "d"]
    assert [r["turn_uuid"] for r in te.read_replies(str(db), "prompts-v2")] == ["a"]


def test_missing_database_is_an_actionable_error(tmp_path):
    with pytest.raises(FileNotFoundError, match="provenance"):
        te.read_replies(str(tmp_path / "nope.db"))


def test_results_are_never_overwritten(tmp_path):
    p = tmp_path / "text_emotion.csv"
    assert te._resolve_out(p) == p
    p.write_text("x", encoding="utf-8")
    second = te._resolve_out(p)
    assert second != p and second.suffix == ".csv" and second.stem.startswith("text_emotion_")


def test_output_fields_cover_both_instruments_and_their_agreement():
    for f in ("clf_quadrant", "clf_match", "lex_quadrant", "lex_match", "agree"):
        assert f in te.FIELDS


def test_macro_f1_weights_every_quadrant_equally():
    """Chapter 4 §4.5 requires macro-F1. Macro, not micro: each quadrant is a class of
    interest and must count equally, or a quadrant the system happens to produce more
    often would dominate the score."""
    rows = [
        {"target_quadrant": "Q1", "clf_quadrant": "Q1"},
        {"target_quadrant": "Q2", "clf_quadrant": "Q2"},
        {"target_quadrant": "Q3", "clf_quadrant": "Q3"},
        {"target_quadrant": "Q4", "clf_quadrant": "Q4"},
    ]
    f1, per = te.macro_f1(rows, "clf_quadrant")
    assert f1 == pytest.approx(1.0)
    assert set(per) == {"Q1", "Q2", "Q3", "Q4"}


def test_macro_f1_gives_no_credit_for_a_neutral_prediction():
    """`-` means the classifier said `neutral`, which is not a quadrant. It must count as
    a false negative, never as a pass."""
    rows = [{"target_quadrant": "Q3", "clf_quadrant": None},
            {"target_quadrant": "Q3", "clf_quadrant": "Q3"}]
    f1, per = te.macro_f1(rows, "clf_quadrant")
    assert per["Q3"] < 1.0
    assert 0.0 < f1 < 1.0
