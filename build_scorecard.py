"""Build the Tier-1 scorecard, the table the engine selection specification leads to.

`TTS_Engine_Selection_Criteria.docx` defines hard filters, machine metrics, a decision rule
and a Table-5 scorecard with one row per engine. Only the table was missing: UTMOS lives in
`naturalness*.csv`, recognised emotion in `emotion*.csv`, dial response in the
controllability report, and none of them were joined. This script builds the table, applies
the declared rule and prints the instrument ceilings beside every figure they bound.

Three design decisions, each learned at a cost
----------------------------------------------

1. The unit is (engine, session), never engine alone. Chatterbox appears in four conditions
   and ZipVoice in three; they differ by a setting, not by engine. Grouping by engine alone
   would average Condition A with Condition C and report a number describing neither. Same
   fault as the `clip_id` collision of 2026-08-09, where the experimental variable was
   missing from the key and a whole comparison was silently overwritten.

2. Unscored engines appear as rows with gaps, never as omissions. Silently dropping engines
   nobody has scored yet would read as if they had been considered and rejected. Coverage
   is part of the result.

3. The naturalness floor is the emotional human anchor, not an invented constant. M2
   measured neutral human speech at 4.057 and emotional human speech at 3.353. The engines
   must produce emotional speech, so the defensible floor is "at least as natural as a human
   being emotional": a measured quantity, not a threshold the author chose, which is the
   objection the criteria document exists to pre-empt.

Valence is reported, never scored. Earlier measurement found it at chance across four
engines, and M1 (2026-08-31) showed why: the recogniser scores valence at 48.8 % on acted
human speech, so the column measures the instrument, not the engine.

    python build_scorecard.py
    python build_scorecard.py --floor-margin 0.2   # widen the naturalness floor

Results are timestamped and never overwritten.
"""

from __future__ import annotations

import argparse
import csv
import glob
import re
import time
from pathlib import Path

from contracts import Quadrant, anchor_for

QUADRANTS = ("Q1", "Q2", "Q3", "Q4")


def load_scored(patterns: "list[str]") -> dict:
    """Join every scored CSV on (session, clip_id); the newest file wins.

    Files are read oldest-first (by mtime), so a later re-scoring of a clip overrides an earlier
    one; blank cells never override. Superseded runs stay on disk under the project's storage
    rule, and preferring the newest is the only reading that matches why they are kept.
    """
    out: dict = {}
    for pat in patterns:
        for path in sorted(glob.glob(pat), key=lambda p: Path(p).stat().st_mtime):
            try:
                rows = list(csv.DictReader(open(path, encoding="utf-8-sig")))
            except Exception:
                continue
            for r in rows:
                key = (r.get("session", ""), r.get("clip_id", ""))
                out.setdefault(key, {}).update({k: v for k, v in r.items() if v != ""})
    return out


def session_settings(session_dir: Path) -> str:
    """Engine settings line from SESSION.md (what distinguishes conditions); '' if absent."""
    md = session_dir / "SESSION.md"
    if not md.exists():
        return ""
    m = re.search(r"\*\*Engine settings:\*\*\s*(.+)", md.read_text(encoding="utf-8"))
    return re.sub(r"[`*]", "", m.group(1)).strip() if m else ""


def load_ceilings(folder: str) -> dict:
    """Newest instrument-ceilings run: the bounds every figure is read against."""
    files = sorted(glob.glob(str(Path(folder) / "*_ceilings_*.txt")))
    if not files:
        return {}
    text = Path(files[-1]).read_text(encoding="utf-8")
    out: dict = {"source": Path(files[-1]).name}
    m = re.search(r"M1 quadrant ([\d.]+)%\s+arousal ([\d.]+)%\s+valence ([\d.]+)%", text)
    if m:
        out.update(quadrant=float(m.group(1)), arousal=float(m.group(2)),
                   valence=float(m.group(3)))
    m = re.search(r"M2 UTMOS natural anchor:\s*([\d.]+)", text)
    if m:
        out["utmos_neutral"] = float(m.group(1))
    return out


def mean_ci(values: "list[float]") -> "tuple[float, float, float]":
    n = len(values)
    if n == 0:
        return float("nan"), float("nan"), float("nan")
    m = sum(values) / n
    if n < 2:
        return m, float("nan"), float("nan")
    var = sum((v - m) ** 2 for v in values) / (n - 1)
    half = 1.96 * (var ** 0.5) / (n ** 0.5)
    return m, m - half, m + half


def summarise(rows: "list[dict]") -> dict:
    """One scorecard row from the clips of one (engine, session)."""
    utmos = [float(r["utmos"]) for r in rows if r.get("utmos")]
    scored = [r for r in rows if r.get("rec_quadrant")]
    quad = aro = val = None
    if scored:
        quad = sum(r["rec_quadrant"] == r["quadrant"] for r in scored) / len(scored)
        ah = vh = 0
        for r in scored:
            tv, ta = anchor_for(Quadrant(r["quadrant"]))
            ah += (float(r["rec_arousal"]) >= 0) == (ta >= 0)
            vh += (float(r["rec_valence"]) >= 0) == (tv >= 0)
        aro, val = ah / len(scored), vh / len(scored)
    m, lo, hi = mean_ci(utmos)
    ok = [r for r in rows if r.get("duration_ok")]
    return {"n": len(rows), "n_utmos": len(utmos), "n_ser": len(scored),
            "utmos": m, "utmos_lo": lo, "utmos_hi": hi,
            "quadrant": quad, "arousal": aro, "valence": val,
            "duration_ok": (sum(r["duration_ok"] == "yes" for r in ok) / len(ok)) if ok else None}


def pct(x) -> str:
    return "  —  " if x is None else f"{x*100:5.1f}"


def num(x) -> str:
    return "  —  " if x != x or x is None else f"{x:5.3f}"


def reference_families(rows: "list[dict]") -> dict:
    """Group scored rows by engine for the engine x reference-level contrast.

    Keyed by (reference set, session), never by reference set alone. Two sessions can share a
    reference set and differ in another setting: `zipvoice_b4_rms01` and `zipvoice_b4_rms00`
    are both `refs=refs_ravdess` and differ only in `target_rms`. Keying on the reference name
    alone silently dropped one of them, the falsified `--target-rms 0` condition: a comparison
    destroyed at display time because the experimental variable was missing from the key.

    Third occurrence of one fault in this project, after the `clip_id` collision of 2026-08-09
    (design without session) and the scorecard grouping fixed by the `(engine, session)` rule.
    The rule each time: whatever varies between two conditions must be in the key that
    separates them.

    Returns {engine: [(reference_set, row), ...]} ordered by reference set, then session, so
    the printed block is stable across runs.
    """
    fam: dict = {}
    for r in rows:
        if "refs=" not in (r.get("settings") or ""):
            continue
        m = re.search(r"refs=(\S+?)(?:,|$)", r["settings"])
        if m:
            fam.setdefault(r["engine"], []).append((m.group(1), r))
    for engine in fam:
        fam[engine].sort(key=lambda pair: (pair[0], pair[1].get("session", "")))
    return fam


def rank_survivors(survivors: "list[dict]") -> "list[dict]":
    """Order the engines that cleared the naturalness floor: quadrant accuracy, then UTMOS.

    Without the secondary key the alphabet picked the winner. Ties on quadrant accuracy fall to
    Python's stable sort, which keeps insertion order, and rows are inserted from
    `sorted(groups.items())`, i.e. alphabetically by engine. On 2026-09-01 `chatterbox_x2_refs`
    and `zipvoice_b4_matched` tied at 60.0 % and Chatterbox printed first only because
    `c` < `z`, despite 0.614 less UTMOS and a confidence interval straddling the floor. The
    Tier-1 winner of the engine comparison was being decided by the alphabet.

    The selection criteria specify a lexicographic rule (naturalness as a hard filter, then
    conveyance) and name no tiebreak. The gap is filled visibly: the printed header names the
    tiebreak.

    UTMOS is the tiebreak because it is the only other metric the criteria declare. Valence is
    excluded because M1 measured the recogniser at 48.8 % on human speech, so it would rank the
    instrument, not the engine; arousal is excluded because four conditions saturate at 100 %
    and it cannot separate them.

    A missing or NaN figure sorts last instead of raising: coverage is part of the result
    (design decision 2), so an unscored engine still appears in the ranking.
    """
    def key(r):
        q, u = r.get("quadrant"), r.get("utmos")
        q = q if isinstance(q, (int, float)) and q == q else -1.0
        u = u if isinstance(u, (int, float)) and u == u else float("-inf")
        return (-q, -u)
    return sorted(survivors, key=key)


def main(argv: "list[str] | None" = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sessions", default="research/sessions")
    ap.add_argument("--ceilings", default="research/instrument_ceilings")
    ap.add_argument("--floor-margin", type=float, default=0.0,
                    help="MOS allowed BELOW the emotional-human anchor before an engine "
                         "fails the naturalness floor (default 0.0 = the anchor itself)")
    ap.add_argument("--out", default="research/scorecard")
    args = ap.parse_args(argv)

    print("Tier-1 scorecard — every admitted engine, every machine metric")
    print("=" * 92)

    scored = load_scored(["research/naturalness*.csv", "research/emotion*.csv"])
    sessions = sorted(Path(args.sessions).glob("*/register.csv"))
    if not sessions:
        print(f"No session registers under {args.sessions}.")
        return 1

    groups: dict = {}
    settings: dict = {}
    for reg in sessions:
        sess = reg.parent.name
        for r in csv.DictReader(open(reg, encoding="utf-8-sig")):
            key = (r["engine"], sess)
            merged = dict(r)
            merged.update(scored.get((sess, r["clip_id"]), {}))
            groups.setdefault(key, []).append(merged)
            settings.setdefault(key, session_settings(reg.parent))

    ceil = load_ceilings(args.ceilings)
    anchor_neutral = ceil.get("utmos_neutral")
    # M2 emotional-human UTMOS anchor is the floor (design decision 3 in the module docstring).
    anchor_emotional = 3.353
    floor = anchor_emotional - args.floor_margin

    print("\nINSTRUMENT CEILINGS — the bounds these figures are read against")
    if ceil:
        print(f"  source: {ceil['source']}")
        print(f"  SER on acted human speech:  quadrant {ceil.get('quadrant', float('nan')):.1f}%  "
              f"arousal {ceil.get('arousal', float('nan')):.1f}%  "
              f"valence {ceil.get('valence', float('nan')):.1f}%  <- valence AT CHANCE")
        print(f"  UTMOS neutral human: {anchor_neutral}   emotional human: {anchor_emotional}")
        print(f"  Naturalness floor in use: {floor:.3f} "
              f"(emotional-human anchor − margin {args.floor_margin})")
    else:
        print("  NONE FOUND — run check_instruments.py. Without ceilings the figures below")
        print("  have no reference point and the valence column cannot be interpreted at all.")

    print("\n" + "-" * 92)
    print(f"  {'engine / condition':<40}{'n':>4}{'UTMOS':>8}{'quad':>7}{'aro':>7}"
          f"{'val*':>7}{'ok%':>7}")
    print("-" * 92)

    rows_out = []
    for (engine, sess), clips in sorted(groups.items()):
        s = summarise(clips)
        label = f"{engine} · {sess.split('_', 2)[-1]}"[:39]
        print(f"  {label:<40}{s['n']:>4}{num(s['utmos']):>8}{pct(s['quadrant']):>7}"
              f"{pct(s['arousal']):>7}{pct(s['valence']):>7}{pct(s['duration_ok']):>7}")
        rows_out.append({"engine": engine, "session": sess,
                         "settings": settings.get((engine, sess), ""), **s})
    print("-" * 92)
    print("  * valence is REPORTED, NEVER SCORED — M1 established the recogniser reads it")
    print("    at chance on human speech, so this column measures the instrument.")

    # --- coverage, stated rather than hidden ------------------------------
    missing_u = [r for r in rows_out if r["n_utmos"] == 0]
    missing_s = [r for r in rows_out if r["n_ser"] == 0]
    if missing_u or missing_s:
        print("\nCOVERAGE GAPS — these rows are incomplete, not rejected:")
        for r in missing_u:
            print(f"  no UTMOS : {r['engine']} · {r['session']}   -> run naturalness.py")
        for r in missing_s:
            print(f"  no SER   : {r['engine']} · {r['session']}   -> run emotion_conveyance.py")

    # --- the decision rule -------------------------------------------------
    print("\n" + "=" * 92)
    print("DECISION RULE (lexicographic with thresholds, per the selection criteria)")
    print("=" * 92)
    eligible = [r for r in rows_out if r["n_utmos"] and r["n_ser"]]
    if not eligible:
        print("  No fully-scored engine yet — the rule cannot be applied.")
    else:
        survivors = [r for r in eligible if r["utmos"] >= floor]
        rejected = [r for r in eligible if r["utmos"] < floor]
        print(f"\n  Step 2 — naturalness floor {floor:.3f}:")
        for r in rejected:
            print(f"    REJECT  {r['engine']} · {r['session']}  UTMOS {r['utmos']:.3f}")
        if not rejected:
            print("    (none rejected)")
        print("\n  Step 3 — survivors ranked by EMOTION CONVEYANCE (quadrant accuracy),")
        print("           ties broken by UTMOS — see rank_survivors() for why:")
        for i, r in enumerate(rank_survivors(survivors), 1):
            print(f"    {i}. {r['engine']:<12} {r['session'].split('_', 2)[-1]:<28}"
                  f" quad {pct(r['quadrant'])}%  UTMOS {r['utmos']:.3f}")
        if ceil.get("arousal"):
            best = max((r["arousal"] or 0) for r in survivors)
            if best * 100 > ceil["arousal"]:
                print(f"\n    NOTE: the best arousal figure ({best*100:.1f}%) EXCEEDS the "
                      f"recogniser's\n    accuracy on human speech ({ceil['arousal']:.1f}%). "
                      "Report it with that stated.")

    # --- factorial contrast ------------------------------------------------
    print("\n" + "=" * 92)
    print("FACTORIAL CONTRAST — engine × reference level")
    print("=" * 92)
    print("  Pairs the same engine against itself across reference sets, so the engine")
    print("  effect and the reference-level effect are separable rather than confounded.")
    fam = reference_families(rows_out)
    if not fam:
        print("\n  No reference-conditioned sessions carry recorded settings yet.")
        print("  (SESSION.md began recording engine settings on 2026-08-31; earlier")
        print("   sessions must be labelled by hand or re-rendered.)")
    else:
        for engine, pairs in sorted(fam.items()):
            print(f"\n  {engine}")
            for ref, r in pairs:
                label = r["session"].split("_", 2)[-1]
                print(f"    {ref:<24} UTMOS {num(r['utmos'])}  quad {pct(r['quadrant'])}%"
                      f"  aro {pct(r['arousal'])}%  n={r['n']}   [{label}]")
            # Spread only across conditions that carry references. `refs=(none)` is the absence
            # of the mechanism, not a reference level, and holds the family's highest UTMOS
            # (Chatterbox 4.336) because an unconditioned voice is the most natural. Including
            # it answers "how far is matched from having no references?" (+0.967) instead of
            # the labelled question "what does changing the reference set buy?" (+0.699).
            withrefs = [r["utmos"] for ref, r in pairs
                        if ref != "(none)" and r["utmos"] == r["utmos"]]
            if len(withrefs) > 1:
                print(f"    reference-level effect on UTMOS: {max(withrefs) - min(withrefs):+.3f}"
                      f"  (across {len(withrefs)} reference sets; `(none)` excluded — it is"
                      f" the absence of the mechanism, not a level of it)")

    # --- persist -----------------------------------------------------------
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    path = out_dir / f"{stamp}_scorecard.csv"
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows_out[0].keys()))
        w.writeheader()
        w.writerows(rows_out)
    print(f"\nWritten (never overwritten): {path}")
    print("This table is Chapter 5's engine comparison; the ceilings above belong beside it.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
