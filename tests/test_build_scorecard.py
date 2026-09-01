"""The Tier-1 scorecard — joining, grouping, coverage and the decision rule.

Three properties carry the project's hard-won lessons and must not regress:

  * the unit is **(engine, session)**, never engine alone — Chatterbox appears in four
    conditions and ZipVoice in three, differing by a *setting*; grouping by engine would
    average Condition A with Condition C and report a number describing neither. Same fault
    as the clip_id collision of 2026-08-09.
  * **unscored engines appear as rows with gaps, never as omissions** — silently dropping
    them would read as though they had been considered and rejected.
  * the naturalness floor is the **measured emotional-human anchor**, not an invented
    constant, because a threshold chosen by the author is the first thing an examiner
    questions.
"""

import csv
import os
import time
from pathlib import Path

import build_scorecard as bs


def _register(d: Path, engine: str, rows):
    d.mkdir(parents=True, exist_ok=True)
    with open(d / "register.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["clip_id", "engine", "param_set", "stimulus_id", "quadrant", "duration_ok"])
        for cid, q, ok in rows:
            w.writerow([cid, engine, "rate_volume_pitch", "S01", q, ok])


def _scored(path: Path, session: str, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["session", "clip_id", "utmos", "rec_quadrant", "rec_valence", "rec_arousal"])
        for cid, u, rq, v, a in rows:
            w.writerow([session, cid, u, rq, v, a])


# --- joining ---------------------------------------------------------------

def test_newest_file_wins_on_the_same_clip(tmp_path, monkeypatch):
    """Superseded runs stay on disk by the storage rule, so preferring the newest is the
    only reading consistent with keeping them."""
    monkeypatch.chdir(tmp_path)
    _scored(Path("research/naturalness_old.csv"), "S", [("c1", "3.000", "Q1", "0.1", "0.1")])
    time.sleep(0.01)
    _scored(Path("research/naturalness_new.csv"), "S", [("c1", "4.500", "Q1", "0.1", "0.1")])
    os.utime("research/naturalness_new.csv", (time.time() + 10, time.time() + 10))
    joined = bs.load_scored(["research/naturalness*.csv"])
    assert joined[("S", "c1")]["utmos"] == "4.500"


def test_blank_values_never_overwrite_a_real_one(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _scored(Path("research/emotion_a.csv"), "S", [("c1", "4.0", "Q1", "0.2", "0.3")])
    _scored(Path("research/emotion_b.csv"), "S", [("c1", "", "", "", "")])
    assert bs.load_scored(["research/emotion*.csv"])[("S", "c1")]["utmos"] == "4.0"


# --- summarising -----------------------------------------------------------

def test_sign_accuracy_uses_the_contract_anchors():
    rows = [{"quadrant": "Q1", "rec_quadrant": "Q1", "rec_valence": "0.5", "rec_arousal": "0.5",
             "utmos": "4.0", "duration_ok": "yes"},
            {"quadrant": "Q3", "rec_quadrant": "Q3", "rec_valence": "-0.5", "rec_arousal": "-0.5",
             "utmos": "4.0", "duration_ok": "yes"}]
    s = bs.summarise(rows)
    assert s["quadrant"] == 1.0 and s["arousal"] == 1.0 and s["valence"] == 1.0


def test_valence_sign_is_counted_against_the_target_not_the_prediction():
    """Q1's anchor is positive valence; a negative reading is wrong even if the quadrant
    label happens to match by luck on the arousal axis."""
    rows = [{"quadrant": "Q1", "rec_quadrant": "Q2", "rec_valence": "-0.4", "rec_arousal": "0.4",
             "utmos": "4.0", "duration_ok": "yes"}]
    s = bs.summarise(rows)
    assert s["valence"] == 0.0 and s["arousal"] == 1.0


def test_unscored_clips_do_not_fabricate_metrics():
    s = bs.summarise([{"quadrant": "Q1", "duration_ok": "yes"}])
    assert s["quadrant"] is None and s["arousal"] is None
    assert s["n"] == 1 and s["n_ser"] == 0 and s["n_utmos"] == 0
    assert s["utmos"] != s["utmos"]                      # NaN, not 0.0


def test_partial_scoring_reports_its_own_denominator():
    rows = [{"quadrant": "Q1", "rec_quadrant": "Q1", "rec_valence": "0.5", "rec_arousal": "0.5",
             "utmos": "4.0", "duration_ok": "yes"},
            {"quadrant": "Q2", "duration_ok": "yes"}]
    s = bs.summarise(rows)
    assert s["n"] == 2 and s["n_ser"] == 1 and s["n_utmos"] == 1
    assert s["quadrant"] == 1.0                          # over the SCORED clips only


# --- grouping: the lesson of the clip_id collision -------------------------

def test_same_engine_in_two_sessions_stays_two_rows(tmp_path, monkeypatch, capsys):
    """Conditions differ by a SETTING, not an engine. Averaging them would report a number
    describing neither."""
    monkeypatch.chdir(tmp_path)
    _register(Path("research/sessions/2026-01-01_0000_cond_a"), "zipvoice",
              [("c1", "Q1", "yes")])
    _register(Path("research/sessions/2026-01-01_0001_cond_b"), "zipvoice",
              [("c2", "Q1", "yes")])
    bs.main(["--sessions", "research/sessions", "--ceilings", "nope",
             "--out", str(tmp_path / "out")])
    out = capsys.readouterr().out
    assert "cond_a" in out and "cond_b" in out


def test_coverage_gaps_are_reported_not_hidden(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    _register(Path("research/sessions/2026-01-01_0000_unscored"), "parlertts",
              [("c1", "Q1", "yes")])
    bs.main(["--sessions", "research/sessions", "--ceilings", "nope",
             "--out", str(tmp_path / "out")])
    out = capsys.readouterr().out
    assert "COVERAGE GAPS" in out and "no UTMOS" in out and "no SER" in out
    assert "parlertts" in out                            # present as a row, not dropped


def test_missing_ceilings_is_called_out(tmp_path, monkeypatch, capsys):
    """Without ceilings the valence column cannot be interpreted at all, and the report
    must say so rather than printing numbers that look self-explanatory."""
    monkeypatch.chdir(tmp_path)
    _register(Path("research/sessions/2026-01-01_0000_x"), "kokoro", [("c1", "Q1", "yes")])
    bs.main(["--sessions", "research/sessions", "--ceilings", "nope",
             "--out", str(tmp_path / "out")])
    assert "NONE FOUND" in capsys.readouterr().out


# --- helpers ---------------------------------------------------------------

def test_ceilings_are_parsed_from_the_newest_run(tmp_path):
    d = tmp_path / "c"
    d.mkdir()
    (d / "20260101-000000_ceilings_n80.txt").write_text(
        "M1 quadrant 30.0%  arousal 70.0%  valence 45.0%\n"
        "M2 UTMOS natural anchor: 3.900 [x]\n", encoding="utf-8")
    (d / "20260102-000000_ceilings_n80.txt").write_text(
        "M1 quadrant 41.2%  arousal 88.8%  valence 48.8%\n"
        "M2 UTMOS natural anchor: 4.057 [3.922, 4.191]\n", encoding="utf-8")
    c = bs.load_ceilings(str(d))
    assert c["arousal"] == 88.8 and c["valence"] == 48.8 and c["utmos_neutral"] == 4.057


def test_settings_line_is_read_from_session_md(tmp_path):
    d = tmp_path / "s"
    d.mkdir()
    (d / "SESSION.md").write_text(
        "- **Engine:** `zipvoice`\n"
        "- **Engine settings:** `refs=refs_ravdess_matched`, `seed=666`\n", encoding="utf-8")
    assert "refs=refs_ravdess_matched" in bs.session_settings(d)
    assert bs.session_settings(tmp_path / "absent") == ""


def test_formatters_never_print_a_misleading_zero():
    assert bs.pct(None).strip() == "—"
    assert bs.num(float("nan")).strip() == "—"
    assert bs.pct(0.412).strip() == "41.2"
def test_ranking_tiebreak_is_utmos_not_the_alphabet():
    """The 2026-09-01 defect: chatterbox and zipvoice tied at 60 % and `c` < `z` decided it.

    Insertion order here is deliberately the alphabetical one the real grouping produces, so
    a regression to a single-key sort fails this test rather than passing by luck.
    """
    survivors = [
        {"engine": "chatterbox", "quadrant": 0.60, "utmos": 3.369},
        {"engine": "zipvoice", "quadrant": 0.60, "utmos": 3.983},
        {"engine": "kokoro", "quadrant": 0.35, "utmos": 4.514},
    ]
    assert [r["engine"] for r in bs.rank_survivors(survivors)] == ["zipvoice", "chatterbox", "kokoro"]


def test_ranking_puts_conveyance_before_naturalness():
    """Lexicographic, not a weighted blend: higher UTMOS never outranks better conveyance."""
    survivors = [
        {"engine": "kokoro", "quadrant": 0.35, "utmos": 4.514},
        {"engine": "zipvoice", "quadrant": 0.60, "utmos": 3.983},
    ]
    assert [r["engine"] for r in bs.rank_survivors(survivors)] == ["zipvoice", "kokoro"]


def test_ranking_sorts_unscored_last_and_never_raises():
    """Coverage is part of the result, so an engine with no figures must still appear."""
    survivors = [
        {"engine": "unscored", "quadrant": None, "utmos": float("nan")},
        {"engine": "zipvoice", "quadrant": 0.60, "utmos": 3.983},
        {"engine": "half", "quadrant": 0.60, "utmos": float("nan")},
    ]
    assert [r["engine"] for r in bs.rank_survivors(survivors)] == ["zipvoice", "half", "unscored"]
def test_reference_families_do_not_collide_on_a_shared_reference_set():
    """zipvoice rms01 and rms00 share `refs=refs_ravdess` and differ only in target_rms.

    Keying on the reference set alone dropped one of them silently — the same fault as the
    2026-08-09 clip_id collision. Both must survive.
    """
    rows = [
        {"engine": "zipvoice", "session": "2026-08-31_0113_zipvoice_b4_rms01",
         "settings": "refs=refs_ravdess, target_rms=0.1", "utmos": 3.463},
        {"engine": "zipvoice", "session": "2026-08-31_0135_zipvoice_b4_rms00",
         "settings": "refs=refs_ravdess, target_rms=0.0", "utmos": 3.246},
    ]
    fam = bs.reference_families(rows)
    assert len(fam["zipvoice"]) == 2
    assert {r["session"] for _, r in fam["zipvoice"]} == {r["session"] for r in rows}


def test_reference_families_skip_rows_without_recorded_settings():
    """A session with no settings line contributes nothing rather than raising."""
    rows = [
        {"engine": "kokoro", "session": "s1", "settings": "", "utmos": 4.5},
        {"engine": "kokoro", "session": "s2", "utmos": 4.5},
        {"engine": "chatterbox", "session": "s3", "settings": "refs=refs, device=cpu", "utmos": 3.4},
    ]
    fam = bs.reference_families(rows)
    assert list(fam) == ["chatterbox"]
    assert fam["chatterbox"][0][0] == "refs"
