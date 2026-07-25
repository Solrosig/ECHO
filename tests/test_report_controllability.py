"""Controllability report tests (Story E6). The statistics are checked on known inputs,
and the end-to-end run uses a synthetic measured-register where each measured correlate
rises monotonically with its intended dial."""

import csv

import report_controllability as rc


def test_spearman_perfect_inverse_and_nonlinear():
    assert rc.spearman([1, 2, 3, 4, 5], [2, 4, 6, 8, 10]) == 1.0
    assert rc.spearman([1, 2, 3, 4, 5], [10, 8, 6, 4, 2]) == -1.0
    assert rc.spearman([1, 2, 3, 4], [1, 4, 9, 16]) == 1.0     # monotonic non-linear


def test_cohens_d_separates_groups():
    d = rc.cohens_d([10, 10.5, 9.5, 10.2], [2, 2.5, 1.5, 2.2])
    assert d > 3.0                                             # clearly separated -> large d


def test_report_end_to_end(tmp_path):
    # full set: measured correlates track the intended dials; neutral = base (all dials 1.0)
    prof = {
        "Q1": (1.18, 0.90, 1.20, 3.0, -6.0, 240),
        "Q2": (1.07, 0.95, 0.96, 2.8, -4.5, 175),
        "Q3": (0.83, 0.71, 0.80, 1.9, -9.9, 150),
        "Q4": (0.93, 0.65, 1.04, 2.2, -11.0, 210),
    }
    rows = []
    for q, (rt, vo, pi, wps, db, f0) in prof.items():
        rows.append({"param_set": "rate_volume_pitch", "quadrant": q, "rate": rt, "volume": vo,
                     "pitch": pi, "words_per_s": wps, "rms_dbfs": db, "f0_hz": f0, "silent": "no"})
        rows.append({"param_set": "neutral", "quadrant": q, "rate": 1.0, "volume": 1.0,
                     "pitch": 1.0, "words_per_s": 2.3, "rms_dbfs": -3.0, "f0_hz": 200, "silent": "no"})
    src = tmp_path / "acoustics.csv"
    with open(src, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["param_set", "quadrant", "rate", "volume", "pitch",
                                          "words_per_s", "rms_dbfs", "f0_hz", "silent"])
        w.writeheader()
        w.writerows(rows)

    out = tmp_path / "controllability.csv"
    assert rc.main(["--acoustics", str(src), "--out", str(out)]) == 0
    assert out.exists()

    recs = list(csv.DictReader(open(out, encoding="utf-8")))
    mono = {r["item"]: float(r["value"]) for r in recs if r["section"] == "monotonicity"}
    assert mono["speaking rate"] > 0.8 and mono["loudness"] > 0.8 and mono["pitch (F0)"] > 0.8
    # separation + effect-size rows are present
    assert any(r["section"] == "separation" for r in recs)
    assert any(r["section"] == "effect_size" for r in recs)
