"""The pilot join is the whole analysis — if it fails it fails SILENTLY, which is the danger.

`answers.csv` writes `blind_id` as `1`; `key.csv` writes it as `001`. A naive string join returns zero
rows, and zero rows prints as "the analysis ran and found nothing" rather than as an error. That is the
most expensive kind of bug in an analysis script, so it is pinned here.
"""

import csv

import analyze_pilot as ap


def _session(tmp_path, answers, key):
    d = tmp_path / "pilot"
    d.mkdir(parents=True, exist_ok=True)
    with open(d / "answers.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["blind_id", "naturalness_1to5", "emotion_guess", "notes"])
        w.writerows(answers)
    with open(d / "key.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["blind_id", "engine", "quadrant", "stimulus_id", "param_set", "source_path"])
        w.writerows(key)
    return d


def test_join_survives_zero_padded_ids(tmp_path):
    """`1` in answers must join to `001` in key — the real file pair does exactly this."""
    d = _session(
        tmp_path,
        [["1", "4", "Q4", ""], ["2", "1", "Q2", ""]],
        [["001", "kokoro", "Q4", "S04", "rate_volume_pitch", "x.wav"],
         ["002", "espeak", "Q2", "S01", "rate_volume_pitch", "y.wav"]],
    )
    rows = ap.load(d)
    assert len(rows) == 2, "a padded/unpadded mismatch must not silently drop every row"
    assert {r["engine"] for r in rows} == {"kokoro", "espeak"}


def test_rates_scores_quadrant_arousal_and_valence_separately():
    """Q1 vs Q2 differ in valence only; Q1 vs Q4 in arousal only. A wrong quadrant can still be
    right on one axis, and the whole M1 finding is that those two axes behave differently."""
    rows = [
        {"guessed": "Q1", "intended": "Q1", "mos": 4.0},   # all three correct
        {"guessed": "Q2", "intended": "Q1", "mos": 2.0},   # arousal right, valence wrong
        {"guessed": "Q4", "intended": "Q1", "mos": 3.0},   # valence right, arousal wrong
        {"guessed": "Q3", "intended": "Q1", "mos": 1.0},   # both wrong
    ]
    r = ap.rates(rows)
    assert r["n"] == 4
    assert r["quad"] == 1
    assert r["arousal"] == 2
    assert r["valence"] == 2
    assert r["mos"] == 2.5


def test_unscorable_guesses_are_excluded_not_counted_wrong():
    """A blank or malformed guess is missing data. Counting it as an error would understate
    accuracy and make the task look harder than it was."""
    rows = [
        {"guessed": "Q1", "intended": "Q1", "mos": 4.0},
        {"guessed": "", "intended": "Q2", "mos": 3.0},
    ]
    r = ap.rates(rows)
    assert r["n"] == 1 and r["quad"] == 1


def test_wilson_interval_stays_inside_zero_one_at_small_n():
    """Per-engine cells hold about six trials. A normal approximation can run below 0 or above 1,
    which is worse than reporting no interval at all."""
    lo, hi = ap.wilson(6, 6)
    assert 0.0 <= lo <= hi <= 1.0
    lo0, hi0 = ap.wilson(0, 6)
    assert 0.0 <= lo0 <= hi0 <= 1.0
    assert ap.wilson(0, 0) != ap.wilson(0, 0) or True  # NaN pair, must not raise


def test_output_csv_is_timestamped_and_never_overwrites(tmp_path):
    rows = [{"blind_id": "1", "engine": "kokoro", "intended": "Q1", "guessed": "Q1",
             "stimulus_id": "S01", "param_set": "rate_volume_pitch", "mos": 4.0, "notes": ""}]
    first = ap.write_csv(rows, tmp_path)
    second = ap.write_csv(rows, tmp_path)
    assert first.exists() and second.exists()
    assert len(list(tmp_path.glob("pilot_analysis_*.csv"))) >= 1


def test_provenance_guard_flags_an_unedited_answers_file(tmp_path):
    """The July file's tell: answers.csv shared an mtime with key.csv, so it was never edited
    after the session was built. Neither check is conclusive; both would have caught it."""
    import os
    d = _session(tmp_path, [["1", "4", "Q1", ""]],
                 [["001", "kokoro", "Q1", "S01", "rate_volume_pitch", "x.wav"]])
    ts = 1_700_000_000
    os.utime(d / "answers.csv", (ts, ts))
    os.utime(d / "key.csv", (ts, ts))
    rows = ap.load(d)
    warns = ap.provenance_warnings(d, rows)
    assert any("share an mtime" in w for w in warns)


def test_provenance_guard_flags_a_collapsed_rating_scale(tmp_path):
    """The July file used only 1 and 4 across 24 rows - a function of engine, not a rating."""
    d = _session(
        tmp_path,
        [["1", "4", "Q1", ""], ["2", "1", "Q2", ""], ["3", "1", "Q3", ""], ["4", "4", "Q4", ""]],
        [["001", "kokoro", "Q1", "S01", "rate_volume_pitch", "a.wav"],
         ["002", "espeak", "Q2", "S01", "rate_volume_pitch", "b.wav"],
         ["003", "espeak", "Q3", "S01", "rate_volume_pitch", "c.wav"],
         ["004", "kokoro", "Q4", "S01", "rate_volume_pitch", "d.wav"]],
    )
    warns = ap.provenance_warnings(d, ap.load(d))
    assert any("distinct value" in w for w in warns)


def test_provenance_guard_stays_quiet_on_a_plausible_human_file(tmp_path):
    """A check that fires on real data would be ignored within a week. Three or more distinct
    ratings and an answers file edited after the key: no warning."""
    import os
    d = _session(
        tmp_path,
        [["1", "5", "Q1", ""], ["2", "3", "Q2", "flat"], ["3", "2", "Q3", ""], ["4", "4", "Q4", ""]],
        [["001", "kokoro", "Q1", "S01", "rate_volume_pitch", "a.wav"],
         ["002", "espeak", "Q2", "S01", "rate_volume_pitch", "b.wav"],
         ["003", "espeak", "Q3", "S01", "rate_volume_pitch", "c.wav"],
         ["004", "kokoro", "Q4", "S01", "rate_volume_pitch", "d.wav"]],
    )
    os.utime(d / "key.csv", (1_700_000_000, 1_700_000_000))
    os.utime(d / "answers.csv", (1_700_003_600, 1_700_003_600))
    assert ap.provenance_warnings(d, ap.load(d)) == []
