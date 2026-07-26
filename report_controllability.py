"""Controllability report (Story E6): does each voice DIAL actually move its acoustic
correlate, and do the four quadrants separate?

Reads the measured register (`acoustics.csv` from analyze_acoustics.py), which carries BOTH
the INTENDED dial values (rate, volume, pitch from the strategy) and the MEASURED correlates
(words_per_s, rms_dbfs, f0_hz). For each dial it reports:
  1. Spearman rank correlation (intended dial -> measured correlate) across all conditions
     -- the monotonicity check: turning the knob up moves the correlate up;
  2. a per-quadrant separation table (mean measured value per quadrant, one param-set);
  3. Cohen's d effect sizes across the affective axis each dial serves.

This is the OBJECTIVE *controllability* verdict (intended-vs-measured), deliberately distinct
from naturalness fidelity (E7). It is literature-grounded twice over: the correlates measured
are the standard acoustic descriptors of each affective dimension -- F0<-pitch, intensity<-
loudness, tempo<-rate (Eyben et al. 2016 GeMAPS; Banse & Scherer 1996; Schröder 2004) -- and
the predicted quadrant orderings come from the same acoustic-correlate literature that the
two-tier mapping was built on. Spearman's (1904) rho and Cohen's (1988) d are the standard
non-parametric association and effect-size statistics, appropriate at this small sample size.
"""

from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from statistics import mean

import numpy as np

# dial -> (intended column, measured column, human label, expected sign)
DIALS = [
    ("rate", "words_per_s", "speaking rate", +1),
    ("volume", "rms_dbfs", "loudness", +1),
    ("pitch", "f0_hz", "pitch (F0)", +1),
]
HIGH_AROUSAL, LOW_AROUSAL = {"Q1", "Q2"}, {"Q3", "Q4"}
POS_VALENCE, NEG_VALENCE = {"Q1", "Q4"}, {"Q2", "Q3"}


def _isnum(v) -> bool:
    try:
        return np.isfinite(float(v))
    except (TypeError, ValueError):
        return False


def _avg(vals) -> float:
    nums = [float(v) for v in vals if _isnum(v)]
    return mean(nums) if nums else 0.0


def _rankdata(a: np.ndarray) -> np.ndarray:
    """Ranks with average ranks for ties (as Spearman requires)."""
    a = np.asarray(a, dtype=float)
    order = np.argsort(a, kind="mergesort")
    ranks = np.empty(len(a), dtype=float)
    ranks[order] = np.arange(1, len(a) + 1)
    sa = a[order]
    i = 0
    while i < len(sa):
        j = i
        while j + 1 < len(sa) and sa[j + 1] == sa[i]:
            j += 1
        if j > i:
            ranks[order[i:j + 1]] = (i + 1 + j + 1) / 2.0
        i = j + 1
    return ranks


def spearman(x, y) -> float:
    """Spearman rank correlation = Pearson on average-ranks. NaN if undefined."""
    x, y = np.asarray(x, float), np.asarray(y, float)
    if len(x) < 2 or len(x) != len(y):
        return float("nan")
    rx, ry = _rankdata(x), _rankdata(y)
    rx = rx - rx.mean()
    ry = ry - ry.mean()
    denom = np.sqrt((rx ** 2).sum() * (ry ** 2).sum())
    return float((rx * ry).sum() / denom) if denom > 0 else float("nan")


def cohens_d(a, b) -> float:
    """Standardized mean difference with pooled SD. NaN if undefined."""
    a, b = np.asarray(a, float), np.asarray(b, float)
    if len(a) < 2 or len(b) < 2:
        return float("nan")
    na, nb = len(a), len(b)
    sp = np.sqrt(((na - 1) * a.var(ddof=1) + (nb - 1) * b.var(ddof=1)) / (na + nb - 2))
    return float((a.mean() - b.mean()) / sp) if sp > 0 else float("nan")


def _resolve_out(path: Path, force: bool) -> Path:
    """Never overwrite: if the target already exists (and --force is not given), return a
    timestamped sibling (..._YYYYMMDD-HHMMSS[-n].csv) so no prior result is ever lost."""
    if force or not path.exists():
        return path
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    cand = path.with_name(f"{path.stem}_{stamp}{path.suffix}")
    i = 1
    while cand.exists():
        cand = path.with_name(f"{path.stem}_{stamp}-{i}{path.suffix}")
        i += 1
    return cand


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--acoustics", default="research/acoustics.csv",
                    help="measured register from analyze_acoustics.py")
    ap.add_argument("--param-set", default="rate_volume_pitch",
                    help="param-set used for separation + effect sizes (the full dial set)")
    ap.add_argument("--out", default=None,
                    help="output CSV (default: controllability.csv beside --acoustics); never overwrites")
    ap.add_argument("--force", action="store_true", help="allow overwriting an existing --out")
    ap.add_argument("--rho-pass", type=float, default=0.5, help="Spearman rho pass threshold")
    args = ap.parse_args(argv)

    src = Path(args.acoustics)
    if not src.exists():
        print(f"Not found: {src}. Run analyze_acoustics.py first to produce it.")
        return 1
    rows = [r for r in csv.DictReader(open(src, encoding="utf-8")) if r.get("silent") != "yes"]
    if not rows:
        print("No audible rows to analyse.")
        return 1

    out: list[dict] = []

    # 1) monotonicity: intended dial -> measured correlate (all conditions)
    print("\n== Controllability: intended dial -> measured correlate (Spearman rho, all conditions) ==")
    print(f"  {'dial':<15}{'intended':<9}{'measured':<12}{'rho':>7}{'n':>5}   verdict")
    for intended, measured, label, sign in DIALS:
        pairs = [(float(r[intended]), float(r[measured])) for r in rows
                 if _isnum(r.get(intended)) and _isnum(r.get(measured))
                 and (measured != "f0_hz" or float(r[measured]) > 0)]
        if len(pairs) < 3:
            print(f"  {label:<15}{intended:<9}{measured:<12}{'n/a':>7}{len(pairs):>5}   (need >=3 pairs)")
            continue
        xs, ys = zip(*pairs)
        rho = spearman(xs, ys)
        ok = rho * sign >= args.rho_pass
        print(f"  {label:<15}{intended:<9}{measured:<12}{rho:7.2f}{len(pairs):>5}   {'PASS' if ok else 'CHECK'}")
        out.append({"section": "monotonicity", "item": label, "measured": measured,
                    "value": round(rho, 3), "n": len(pairs), "note": "PASS" if ok else "CHECK"})

    # choose the param-set for separation + effect sizes
    counts: dict[str, int] = defaultdict(int)
    for r in rows:
        counts[r.get("param_set", "?")] += 1
    ps = args.param_set if any(r.get("param_set") == args.param_set for r in rows) \
        else max(counts, key=counts.get)
    full = [r for r in rows if r.get("param_set") == ps]

    # 2) per-quadrant separation
    print(f"\n== Per-quadrant separation (param-set '{ps}') ==")
    print(f"  {'quad':<6}{'F0 Hz':>8}{'words/s':>9}{'RMS dB':>8}{'n':>5}")
    for q in sorted({r.get("quadrant", "?") for r in full}):
        g = [r for r in full if r.get("quadrant") == q]
        f0 = _avg([r["f0_hz"] for r in g if _isnum(r.get("f0_hz")) and float(r["f0_hz"]) > 0])
        wps, db = _avg([r.get("words_per_s") for r in g]), _avg([r.get("rms_dbfs") for r in g])
        print(f"  {q:<6}{f0:8.1f}{wps:9.2f}{db:8.1f}{len(g):5d}")
        out.append({"section": "separation", "item": q, "measured": "",
                    "value": "", "n": len(g), "note": f"F0={f0:.1f};wps={wps:.2f};db={db:.1f}"})

    # 3) effect sizes across the axis each dial serves
    def vals(qset, key):
        return [float(r[key]) for r in full if r.get("quadrant") in qset
                and _isnum(r.get(key)) and (key != "f0_hz" or float(r[key]) > 0)]
    print(f"\n== Effect sizes (Cohen's d, param-set '{ps}') ==")
    checks = [
        ("rate: high-vs-low arousal", "words_per_s", HIGH_AROUSAL, LOW_AROUSAL),
        ("loudness: high-vs-low arousal", "rms_dbfs", HIGH_AROUSAL, LOW_AROUSAL),
        ("pitch: pos-vs-neg valence", "f0_hz", POS_VALENCE, NEG_VALENCE),
    ]
    for label, key, ga, gb in checks:
        d = cohens_d(vals(ga, key), vals(gb, key))
        print(f"  {label:<34}{d:6.2f}")
        out.append({"section": "effect_size", "item": label, "measured": key,
                    "value": round(d, 3) if d == d else "", "n": "", "note": ""})

    dest = Path(args.out) if args.out else src.parent / "controllability.csv"
    dest = _resolve_out(dest, args.force)
    dest.parent.mkdir(parents=True, exist_ok=True)
    with open(dest, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["section", "item", "measured", "value", "n", "note"])
        w.writeheader()
        w.writerows(out)
    print(f"\nWrote {dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
