"""Layer 3 — cross-modal agreement (story C2).

The SER is never loaded here. What matters for the research claim is that kappa is
chance-corrected, that abstentions are excluded rather than counted as disagreement, and
that both text instruments are carried separately.
"""

import csv

import pytest

import cross_modal as cm


# --- Cohen's kappa -------------------------------------------------------------

def test_perfect_agreement_is_one():
    k, po, pe = cm.cohens_kappa([("Q1", "Q1"), ("Q2", "Q2"), ("Q3", "Q3")])
    assert k == pytest.approx(1.0)
    assert po == pytest.approx(1.0)


def test_total_disagreement_is_negative():
    k, _, _ = cm.cohens_kappa([("Q1", "Q2"), ("Q2", "Q1"), ("Q1", "Q2"), ("Q2", "Q1")])
    assert k < 0


def test_kappa_discounts_agreement_that_chance_explains():
    """The reason kappa is used at all: two raters that both mostly say Q4 agree often by
    accident, and raw agreement would report that as success."""
    pairs = [("Q4", "Q4")] * 9 + [("Q1", "Q4")]
    k, po, pe = cm.cohens_kappa(pairs)
    assert po == pytest.approx(0.9)          # looks excellent
    assert pe > 0.8                          # but chance explains nearly all of it
    assert k < 0.5                           # so kappa is much lower


def test_constant_raters_give_undefined_kappa_not_a_crash():
    import math
    k, po, _ = cm.cohens_kappa([("Q4", "Q4")] * 5)
    assert math.isnan(k)                     # undefined, not 1.0
    assert po == pytest.approx(1.0)


def test_empty_input_is_nan_not_an_exception():
    import math
    k, po, pe = cm.cohens_kappa([])
    assert math.isnan(k) and math.isnan(po) and math.isnan(pe)


# --- plumbing ------------------------------------------------------------------

def test_windows_paths_resolve_on_any_platform():
    assert cm._norm_path("audio_out\\abc_Q1.wav").name == "abc_Q1.wav"


def test_newest_layer1_ignores_superseded_runs(tmp_path):
    (tmp_path / "text_emotion_20260830-superseded_placeholder-norms.csv").write_text("x")
    good = tmp_path / "text_emotion_20260830-190846.csv"
    good.write_text("y")
    assert cm.newest_layer1(str(tmp_path)) == good


def test_newest_layer1_returns_none_when_there_is_nothing(tmp_path):
    assert cm.newest_layer1(str(tmp_path)) is None


def test_turns_without_audio_or_reply_are_not_read(tmp_path):
    import sqlite3
    db = tmp_path / "t.db"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE turns (turn_uuid TEXT, ts TEXT, quadrant TEXT, reply TEXT, "
                 "audio_path TEXT, prompt_version TEXT)")
    conn.executemany("INSERT INTO turns VALUES (?,?,?,?,?,?)", [
        ("a", "1", "Q1", "hello", "audio_out/a.wav", "prompts-v2"),
        ("b", "2", "Q2", "", "audio_out/b.wav", "prompts-v2"),      # no reply
        ("c", "3", "Q3", "hi", None, "prompts-v2"),                 # no audio
    ])
    conn.commit(); conn.close()
    assert [t["turn_uuid"] for t in cm.read_turns(str(db))] == ["a"]


def test_missing_database_is_an_actionable_error(tmp_path):
    with pytest.raises(FileNotFoundError, match="provenance"):
        cm.read_turns(str(tmp_path / "nope.db"))


def test_results_are_never_overwritten(tmp_path):
    p = tmp_path / "cross_modal.csv"
    assert cm._resolve_out(p) == p
    p.write_text("x", encoding="utf-8")
    assert cm._resolve_out(p) != p


def test_output_carries_both_text_instruments_separately():
    """They agreed on only 6.2% of replies, so neither may stand in for 'the' text side."""
    for f in ("text_clf_quadrant", "text_lex_quadrant",
              "clf_ser_agree", "lex_ser_agree",
              "joint_correct_clf", "joint_correct_lex"):
        assert f in cm.FIELDS


def test_ser_contract_keys_are_the_ones_this_module_reads():
    """Pins the seam between Layer 2 and Layer 3.

    cross_modal.py consumes predict_va()'s dict directly. The first run failed with
    KeyError: 'valence' because the keys are rec_valence / rec_arousal / rec_dominance,
    already on [-1, 1]. Reading the source rather than calling it keeps the SER unloaded.
    """
    import inspect

    import emotion_conveyance as ec

    src = inspect.getsource(ec.predict_va)
    for key in ("rec_valence", "rec_arousal", "rec_dominance"):
        assert f'"{key}"' in src, f"predict_va no longer returns {key}"

    consumer = inspect.getsource(cm.main)
    assert 'va["rec_valence"]' in consumer and 'va["rec_arousal"]' in consumer
