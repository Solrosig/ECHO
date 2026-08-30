"""Layer 3 — cross-modal agreement between the TEXT and the SPEECH of the same turn.

Chapter 4 §4.5 calls this layer "the direct response to Gap 3": cross-modal coherence
between generated text and synthesised speech is rarely measured directly. Layers 1 and 2
each classify one channel; this one asks whether they agree, and reports **Cohen's kappa**
so the agreement is chance-corrected rather than inflated by a shared bias toward one
quadrant.

Three design points.

**It runs per TURN, not per corpus clip.** The 280-clip evaluation corpus deliberately holds
text constant and bypasses the LLM, so it has no text channel to compare against. Only the
`echo.db` turns have both a generated reply and its rendered audio, so they are the only
material on which cross-modal agreement is defined.

**Kappa is reported PER TEXT INSTRUMENT.** Measured 2026-08-30, the classifier and the
lexicon score identically (31.2%) yet agree with each other on only 6.2% of replies.
Choosing one and calling it "the" text classification would be arbitrary, so both are
carried through and compared with the speech side separately.

**Abstentions are excluded from kappa and counted.** A `neutral` classification or a lexicon
with no rated vocabulary is an absence of evidence, not a disagreement; folding it in as a
mismatch would understate agreement. The excluded count is always printed.

Usage:
    python cross_modal.py
    python cross_modal.py --layer1 research/text_emotion_20260830-190846.csv
    python cross_modal.py --model ser_model          # local SER copy
"""

from __future__ import annotations

import argparse
import csv
import sqlite3
from collections import Counter
from datetime import datetime
from pathlib import Path

from config import load_config
from contracts import Quadrant, anchor_for
from judge import LexiconJudge, load_norms

QUADS = [q.value for q in Quadrant]
FIELDS = ["turn_uuid", "target_quadrant", "reply", "audio_path",
          "text_clf_quadrant", "text_lex_quadrant",
          "lex_valence", "lex_arousal", "lex_hits",
          "ser_valence", "ser_arousal", "ser_quadrant",
          "target_valence", "target_arousal",
          "ser_displacement", "lex_displacement",
          "clf_ser_agree", "lex_ser_agree", "joint_correct_clf", "joint_correct_lex"]


def cohens_kappa(pairs: list[tuple[str, str]]) -> tuple[float, float, float]:
    """Chance-corrected agreement between two raters over the same items.

    Returns (kappa, observed agreement, expected agreement). Kappa is used rather than raw
    agreement because two raters that both favour one quadrant would agree often by
    accident: with a shared bias, a high percentage means little. Landis & Koch's rough
    bands -- <0 none, 0-.20 slight, .21-.40 fair, .41-.60 moderate, .61-.80 substantial --
    are conventional, not authoritative.
    """
    n = len(pairs)
    if n == 0:
        return float("nan"), float("nan"), float("nan")
    observed = sum(1 for a, b in pairs if a == b) / n
    a_counts, b_counts = Counter(a for a, _ in pairs), Counter(b for _, b in pairs)
    labels = set(a_counts) | set(b_counts)
    expected = sum((a_counts[l] / n) * (b_counts[l] / n) for l in labels)
    if expected >= 1.0:                       # both raters constant on the same label
        return float("nan"), observed, expected
    return (observed - expected) / (1 - expected), observed, expected


def displacement(v: float, a: float, target: str) -> float:
    """Euclidean distance from the recognised point to the target anchor.

    Chapter 4 §4.5 specifies displacement for Layer 4 ("mean displacement from the target
    anchor ... with 95% confidence intervals"). The machine layers use the same measure so
    that machine and human results are comparable at RQ4, and because it does not have the
    failure mode quadrant labels do: assignment thresholds at exactly zero, while the SER's
    recognised valence is compressed into roughly +/-0.3 against targets at +/-0.6, so a
    sign flip near the origin turns a weak-but-real estimate into a coin toss. Distance
    keeps the magnitude the label discards.
    """
    tv, ta = anchor_for(Quadrant(target))
    return ((v - tv) ** 2 + (a - ta) ** 2) ** 0.5


def mean_ci(xs: list[float]) -> tuple[float, float, float]:
    """Mean with a normal-approximation 95% interval. Returns (mean, lo, hi)."""
    n = len(xs)
    if n == 0:
        return float("nan"), float("nan"), float("nan")
    m = sum(xs) / n
    if n < 2:
        return m, float("nan"), float("nan")
    var = sum((x - m) ** 2 for x in xs) / (n - 1)
    half = 1.96 * (var ** 0.5) / (n ** 0.5)
    return m, m - half, m + half


def _norm_path(p: str) -> Path:
    """Registers and turns are written on Windows; normalise for any platform."""
    return Path(str(p).replace("\\", "/"))


def read_turns(db_path: str, prompt_version: str | None = None) -> list[dict]:
    if not Path(db_path).exists():
        raise FileNotFoundError(f"no provenance database at {db_path}")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    sql = ("SELECT turn_uuid, quadrant, reply, audio_path FROM turns "
           "WHERE reply IS NOT NULL AND TRIM(reply) <> '' AND audio_path IS NOT NULL")
    args: list = []
    if prompt_version:
        sql += " AND prompt_version = ?"
        args.append(prompt_version)
    try:
        return [dict(r) for r in conn.execute(sql + " ORDER BY ts", args)]
    finally:
        conn.close()


def newest_layer1(folder: str = "research") -> Path | None:
    """The most recent Layer 1 output, excluding runs marked superseded."""
    cands = [p for p in Path(folder).glob("text_emotion*.csv") if "superseded" not in p.name]
    return max(cands, key=lambda p: p.stat().st_mtime) if cands else None


def read_layer1(path: Path) -> dict[str, dict]:
    with open(path, newline="", encoding="utf-8") as fh:
        return {r["turn_uuid"]: r for r in csv.DictReader(fh)}


def _resolve_out(path: Path) -> Path:
    if not path.exists():
        return path
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return path.with_name(f"{path.stem}_{stamp}{path.suffix}")


def _crosstab(rows: list[dict], text_key: str) -> None:
    """text quadrant (rows) against speech quadrant (columns)."""
    counts = Counter((r[text_key] or "-", r["ser_quadrant"] or "-") for r in rows)
    cols = QUADS + ["-"]
    print("   text\\speech" + "".join(f"{c:>6}" for c in cols))
    for t in cols:
        n = sum(counts[(t, c)] for c in cols)
        if n:
            print(f"        {t:<5}" + "".join(f"{counts[(t, c)]:>6}" for c in cols))


def _report(rows: list[dict], text_key: str, label: str) -> None:
    pairs = [(r[text_key], r["ser_quadrant"]) for r in rows
             if r[text_key] and r["ser_quadrant"]]
    excluded = len(rows) - len(pairs)
    k, po, pe = cohens_kappa(pairs)
    print(f"\n=== Layer 3: {label} vs speech (SER) ===")
    _crosstab(rows, text_key)
    print(f"  usable pairs      : {len(pairs)}/{len(rows)}  ({excluded} excluded: no opinion)")
    if pairs:
        print(f"  observed agreement: {100*po:5.1f}%")
        print(f"  expected by chance: {100*pe:5.1f}%")
        print(f"  Cohen's kappa     : {k:+.3f}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", default="echo.db")
    ap.add_argument("--layer1", default="", help="Layer 1 CSV (default: newest in research/)")
    ap.add_argument("--model", default=None, help="SER model id or local folder")
    ap.add_argument("--prompt-version", default=None)
    ap.add_argument("--out", default="research/cross_modal.csv")
    args = ap.parse_args(argv)

    l1_path = Path(args.layer1) if args.layer1 else newest_layer1()
    if l1_path is None or not l1_path.exists():
        print("No Layer 1 output found. Run text_emotion.py first.")
        return 1
    layer1 = read_layer1(l1_path)
    print(f"Layer 1: {l1_path}  ({len(layer1)} classified replies)")

    turns = read_turns(args.db, args.prompt_version)
    turns = [t for t in turns if t["turn_uuid"] in layer1]
    if not turns:
        print("No turns have both a Layer 1 classification and audio.")
        return 1

    from emotion_conveyance import predict_va, quadrant_of, spearman   # lazy: heavy deps
    lex = LexiconJudge(load_norms(load_config().affect_norms or None))
    print(f"Layer 2: scoring {len(turns)} clips with the dimensional SER ...")

    rows: list[dict] = []
    missing = 0
    for t in turns:
        wav = _norm_path(t["audio_path"])
        if not wav.exists():
            missing += 1
            continue
        va = predict_va(wav, args.model)
        # emotion_conveyance.predict_va() returns rec_valence / rec_arousal / rec_dominance,
        # ALREADY on ECHO's [-1, 1] axes — not `valence`/`arousal`, and not 0..1.
        # Pinned by test_ser_contract_keys_are_the_ones_this_module_reads.
        v, a = float(va["rec_valence"]), float(va["rec_arousal"])
        sq = quadrant_of(v, a)
        l1 = layer1[t["turn_uuid"]]
        clf, lexq = l1.get("clf_quadrant") or None, l1.get("lex_quadrant") or None
        lv, la, hits = lex.score(t["reply"])
        tv, ta = anchor_for(Quadrant(t["quadrant"]))
        rows.append({
            "turn_uuid": t["turn_uuid"], "target_quadrant": t["quadrant"],
            "reply": t["reply"], "audio_path": str(wav),
            "text_clf_quadrant": clf, "text_lex_quadrant": lexq,
            "lex_valence": round(lv, 4), "lex_arousal": round(la, 4), "lex_hits": hits,
            "ser_valence": round(v, 4), "ser_arousal": round(a, 4), "ser_quadrant": sq,
            "target_valence": tv, "target_arousal": ta,
            "ser_displacement": round(displacement(v, a, t["quadrant"]), 4),
            "lex_displacement": round(displacement(lv, la, t["quadrant"]), 4) if hits else "",
            "clf_ser_agree": int(clf is not None and clf == sq),
            "lex_ser_agree": int(lexq is not None and lexq == sq),
            "joint_correct_clf": int(clf == t["quadrant"] and sq == t["quadrant"]),
            "joint_correct_lex": int(lexq == t["quadrant"] and sq == t["quadrant"]),
        })
    if missing:
        print(f"  ({missing} turn(s) skipped — audio file not found)")
    if not rows:
        print("No turns had readable audio.")
        return 1

    out = _resolve_out(Path(args.out))
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)

    _report(rows, "text_clf_quadrant", "classifier")
    _report(rows, "text_lex_quadrant", "lexicon")

    # --- continuous comparison: the measure the quadrant label throws away ----------
    both = [r for r in rows if r["lex_hits"]]
    if len(both) >= 3:
        sv = spearman([r["lex_valence"] for r in both], [r["ser_valence"] for r in both])
        sa = spearman([r["lex_arousal"] for r in both], [r["ser_arousal"] for r in both])
        print("\n=== Layer 3 (continuous): lexicon vs SER, per axis ===")
        print(f"  n with lexicon evidence : {len(both)}/{len(rows)}")
        print(f"  Spearman rho, valence   : {sv:+.3f}")
        print(f"  Spearman rho, arousal   : {sa:+.3f}")
        print("  Both instruments are dimensional here, so this is a like-for-like")
        print("  comparison; the classifier has no continuous output to compare.")

    print("\n=== Displacement from the target anchor (lower is better) ===")
    sm, slo, shi = mean_ci([r["ser_displacement"] for r in rows])
    print(f"  speech (SER) : {sm:.3f}   95% CI [{slo:.3f}, {shi:.3f}]   n={len(rows)}")
    ld = [r["lex_displacement"] for r in rows if r["lex_displacement"] != ""]
    if ld:
        lm, llo, lhi = mean_ci(ld)
        print(f"  text (lexicon): {lm:.3f}   95% CI [{llo:.3f}, {lhi:.3f}]   n={len(ld)}")
    print("  For reference: a point at the ORIGIN is 0.849 from any anchor (+/-0.6, +/-0.6);")
    print("  the far corner is 1.697. Above ~0.849 means worse than saying 'neutral'.")

    n = len(rows)
    jc = 100.0 * sum(r["joint_correct_clf"] for r in rows) / n
    jl = 100.0 * sum(r["joint_correct_lex"] for r in rows) / n
    print("\n=== Joint accuracy (BOTH channels match the user's target) ===")
    print(f"  classifier + speech : {jc:5.1f}%")
    print(f"  lexicon + speech    : {jl:5.1f}%")
    print("\nGap 3 is addressed by the kappa figures above: they measure agreement between")
    print("the two channels directly, chance-corrected, rather than each against the target.")
    print(f"\nwritten: {out}   ({n} rows)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
