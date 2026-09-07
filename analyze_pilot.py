"""Score a completed listening pre-test — with provenance checked before any statistic is quoted.

    python analyze_pilot.py --session research/listening/<stamp>_pilot

Why this exists
---------------
The riskiest assumption in the whole listening study is **not** "are five listeners enough". It is
**"can a listener identify the intended quadrant from these clips at all?"** If the answer is no, the
finding is that the task was too hard — and at n = 5 that discovery arrives after the panel is spent,
with no second run available. A pre-test answers it for the price of one evening.

**Why it also checks provenance.** This tool was first written against
`research/listening/2026-07-29_1946_pilot/`, whose `answers.csv` looked like 24 completed human
judgements. It contained none: **nobody took that test**, and the values were placeholder. A full set
of findings was reported and then retracted on 2026-09-06.

Two tells were visible before a single statistic was computed — `answers.csv` shared an mtime with
`key.csv`, and the "five-point" scale took two values — and **neither was looked at, because every
check performed was a check of the analysis rather than of the data.** `provenance_warnings()` now
runs first and prints above the results. See `LISTENING_PRETEST_GUIDE.md` for how to produce a session
this tool can legitimately score.

What it reports
---------------
* quadrant accuracy against a 25 % chance level, with a Wilson interval, overall and per engine;
* **arousal-sign** and **valence-sign** accuracy against 50 % — the split that M1 showed matters, since
  the machine reads arousal at 88.8 % and valence at 48.8 % on ground-truth human speech;
* mean naturalness (1–5), comparable in spirit to the UTMOS ranking though not on the same scale;
* the intended x guessed confusion matrix, which is where a mechanism is visible rather than a number;
* the machine's own quadrant accuracy for the same engines, printed alongside, so **human and machine
  disagreement is visible in the one place it can be seen without running the panel**.

Results are timestamped and never overwrite.
"""

from __future__ import annotations

import argparse
import csv
import math
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

QUADRANTS = ("Q1", "Q2", "Q3", "Q4")

#: Q1 happy, Q2 upset, Q3 sad, Q4 calm -- the anchors in `contracts.py` (va-anchors-v1).
HIGH_AROUSAL = {"Q1", "Q2"}
POSITIVE_VALENCE = {"Q1", "Q4"}

#: Machine quadrant accuracy from research/scorecard/, for the engines the pilot happens to cover.
#: Printed for comparison only -- the pilot used whatever clips were current in July, so these are
#: the same ENGINES rather than guaranteed the same CLIPS.
MACHINE_QUADRANT = {
    "kokoro": 0.35,
    "espeak": 0.40,
    "sapi5xml": 0.425,
    "chatterbox": 0.35,
}

#: M1 instrument ceilings on acted human speech -- the bound every figure here is read against.
CEILING = {"quadrant": 0.412, "arousal": 0.888, "valence": 0.488}


def normalise_id(raw: str) -> str:
    """`answers.csv` writes `1`, `key.csv` writes `001`. Join on the integer, not the string.

    This is not a formatting nicety. A silent join failure would produce an empty result set, and an
    empty result set reads exactly like "the analysis ran and found nothing" -- which is the most
    expensive kind of bug in an analysis script.
    """
    return str(int(str(raw).strip()))


def wilson(k: int, n: int, z: float = 1.96) -> "tuple[float, float]":
    """Wilson score interval -- correct for small n, unlike the normal approximation.

    The per-engine cells here hold about six trials each. A normal-approximation interval on n = 6
    can extend below 0 or above 1, which would be worse than reporting no interval at all.
    """
    if n == 0:
        return (float("nan"), float("nan"))
    p = k / n
    d = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / d
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, centre - half), min(1.0, centre + half))


def provenance_warnings(session: Path, rows: "list[dict]") -> "list[str]":
    """Cheap checks for "these values were never typed by a person".

    Added 2026-09-06 after the July `answers.csv` was analysed, reported, and then confirmed to
    contain no human judgements at all. Two tells were visible before any statistic was computed
    and neither was looked at:

      * **`answers.csv` shares an mtime with `key.csv`.** `make_listening_test.py --build` writes
        both in one call, so equal mtimes mean the answers file was never edited after creation.
        A person filling in two dozen rows leaves it later than the key.
      * **the 1-5 scale takes fewer than three distinct values.** The July file used only 1 and 4,
        resolving to exactly 4.00 for one engine and exactly 1.00 for the others -- a function of
        engine, not a rating.

    Neither check is conclusive: a fast rater could conceivably use two values, and a filesystem
    copy can flatten mtimes. Both are warnings, not errors, and both are printed ABOVE the
    results, because that is where an over-reading would otherwise happen. **A check that fires
    spuriously costs a sentence of explanation; a check that never fires costs a retraction.**
    """
    out = []
    try:
        a, k = session / "answers.csv", session / "key.csv"
        if a.exists() and k.exists() and int(a.stat().st_mtime) == int(k.stat().st_mtime):
            out.append("answers.csv and key.csv share an mtime — answers.csv looks unedited "
                       "since the session was built, i.e. possibly never filled in by a person.")
    except OSError:
        pass
    scale = {r["mos"] for r in rows if r["mos"] is not None}
    if rows and len(scale) < 3:
        out.append(f"the 1-5 naturalness scale takes only {len(scale)} distinct value(s) "
                   f"{sorted(scale)} — a human rating rarely collapses this far.")
    return out


def load(session: Path) -> "list[dict]":
    key = {normalise_id(r["blind_id"]): r
           for r in csv.DictReader(open(session / "key.csv", encoding="utf-8"))}
    rows = []
    for a in csv.DictReader(open(session / "answers.csv", encoding="utf-8")):
        k = key.get(normalise_id(a["blind_id"]))
        if k is None:
            continue
        guess = (a.get("emotion_guess") or "").strip().upper()
        try:
            mos = float(a["naturalness_1to5"])
        except (TypeError, ValueError):
            mos = None
        rows.append({
            "blind_id": normalise_id(a["blind_id"]),
            "engine": k["engine"], "intended": k["quadrant"],
            "stimulus_id": k["stimulus_id"], "param_set": k["param_set"],
            "guessed": guess if guess in QUADRANTS else "",
            "mos": mos, "notes": (a.get("notes") or "").strip(),
        })
    return rows


def rates(rows: "list[dict]") -> dict:
    scored = [r for r in rows if r["guessed"]]
    n = len(scored)
    quad = sum(1 for r in scored if r["guessed"] == r["intended"])
    aro = sum(1 for r in scored
              if (r["guessed"] in HIGH_AROUSAL) == (r["intended"] in HIGH_AROUSAL))
    val = sum(1 for r in scored
              if (r["guessed"] in POSITIVE_VALENCE) == (r["intended"] in POSITIVE_VALENCE))
    mos = [r["mos"] for r in scored if r["mos"] is not None]
    return {"n": n, "quad": quad, "arousal": aro, "valence": val,
            "mos": (sum(mos) / len(mos)) if mos else None}


def pct(k: int, n: int) -> str:
    return f"{100.0 * k / n:5.1f}%" if n else "    —"


def report(rows: "list[dict]", warnings: "list[str] | None" = None) -> None:
    print("=" * 78)
    print("PILOT LISTENING TEST")
    print("=" * 78)
    for w in (warnings or []):
        print(f"  !! PROVENANCE WARNING: {w}")
    if warnings:
        print("  !! Establish who produced these values before quoting any figure below.")
        print()
    print("  SCOPE. `answers.csv` records no participant, so this tool cannot tell one")
    print("  listener from several. If the session was ONE person, the intervals below treat")
    print("  their trials as independent draws — they are not, and for 'can LISTENERS do")
    print("  this?' the effective n is 1: a demonstration, not an estimate. Record the")
    print("  listener, their naivety to the design, and the date in SESSION_NOTES.md.")
    print()

    overall = rates(rows)
    n = overall["n"]
    lo, hi = wilson(overall["quad"], n)
    print(f"  Trials scored: {n} of {len(rows)} joined")
    print()
    print(f"  {'measure':<18}{'accuracy':>10}{'chance':>9}{'95% CI':>18}{'human ceiling (M1)':>21}")
    print("  " + "-" * 74)
    print(f"  {'quadrant':<18}{pct(overall['quad'], n):>10}{'25%':>9}"
          f"{f'[{lo * 100:.1f}, {hi * 100:.1f}]':>18}{CEILING['quadrant'] * 100:>20.1f}%")
    alo, ahi = wilson(overall["arousal"], n)
    print(f"  {'arousal sign':<18}{pct(overall['arousal'], n):>10}{'50%':>9}"
          f"{f'[{alo * 100:.1f}, {ahi * 100:.1f}]':>18}{CEILING['arousal'] * 100:>20.1f}%")
    vlo, vhi = wilson(overall["valence"], n)
    print(f"  {'valence sign':<18}{pct(overall['valence'], n):>10}{'50%':>9}"
          f"{f'[{vlo * 100:.1f}, {vhi * 100:.1f}]':>18}{CEILING['valence'] * 100:>20.1f}%")
    if overall["mos"] is not None:
        print(f"  {'mean naturalness':<18}{overall['mos']:>9.2f}{'(1-5)':>9}")

    print()
    print("  READING IT: a quadrant CI clear of 25 % means THIS listener beat their own")
    print("  chance level. It does not estimate what five naive listeners will do — that")
    print("  needs the dry run, which is the first naive-listener data the project will have.")
    print("  If valence-sign sits near 50 % while arousal-sign is well above it, this")
    print("  listener shows the SAME asymmetry the machine does — worth testing properly.")

    print()
    print("=" * 78)
    print("PER ENGINE — cells are tiny; read the intervals, not the point estimates")
    print("=" * 78)
    by = defaultdict(list)
    for r in rows:
        by[r["engine"]].append(r)
    print(f"  {'engine':<14}{'n':>4}{'quad':>8}{'95% CI':>16}{'aro':>8}{'val':>8}"
          f"{'MOS':>7}{'machine quad':>15}")
    print("  " + "-" * 78)
    for engine in sorted(by):
        e = rates(by[engine])
        elo, ehi = wilson(e["quad"], e["n"])
        m = MACHINE_QUADRANT.get(engine)
        # Built before the f-string: nesting the same quote inside an f-string needs Python 3.12
        # (PEP 701), and this project must stay readable to the 3.10 that the CI-less sandbox runs.
        ci = f"[{elo * 100:.0f}, {ehi * 100:.0f}]"
        mos_s = f"{e['mos']:.2f}" if e["mos"] is not None else "—"
        machine_s = f"{m * 100:.1f}%" if m is not None else "—"
        print(f"  {engine:<14}{e['n']:>4}{pct(e['quad'], e['n']):>8}{ci:>16}"
              f"{pct(e['arousal'], e['n']):>8}{pct(e['valence'], e['n']):>8}"
              f"{mos_s:>7}{machine_s:>15}")

    print()
    print("=" * 78)
    print("CONFUSION — rows = intended, cols = guessed")
    print("=" * 78)
    cm = Counter((r["intended"], r["guessed"]) for r in rows if r["guessed"])
    print("        " + "".join(f"{q:>6}" for q in QUADRANTS) + f"{'n':>6}{'acc':>7}")
    for qi in QUADRANTS:
        row = [cm.get((qi, qj), 0) for qj in QUADRANTS]
        tot = sum(row)
        acc = pct(cm.get((qi, qi), 0), tot) if tot else "    —"
        print(f"  {qi:<6}" + "".join(f"{c:>6}" for c in row) + f"{tot:>6}{acc:>7}")


def write_csv(rows: "list[dict]", out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"pilot_analysis_{datetime.now().strftime('%Y%m%d-%H%M%S')}.csv"
    fields = ["blind_id", "engine", "intended", "guessed", "stimulus_id",
              "param_set", "mos", "notes"]
    with open(out, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        w.writerows({k: r[k] for k in fields} for r in rows)
    return out


def main(argv: "list[str] | None" = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--session", default="research/listening/2026-07-29_1946_pilot")
    ap.add_argument("--out-dir", default="research/listening")
    args = ap.parse_args(argv)

    session = Path(args.session)
    if not (session / "answers.csv").exists() or not (session / "key.csv").exists():
        print(f"Need answers.csv and key.csv in {session}")
        return 1

    rows = load(session)
    if not rows:
        print("No rows joined — check that blind_id values correspond in the two files.")
        return 1

    report(rows, provenance_warnings(session, rows))
    out = write_csv(rows, Path(args.out_dir))
    print()
    print(f"Joined rows written (never overwritten): {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
