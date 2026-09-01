"""Instrument ceilings — what the objective instruments score on GROUND-TRUTH human speech.

Why this is the highest-value analysis in the project
-----------------------------------------------------
ECHO's central finding is that **arousal transmits acoustically and valence does not**,
reproduced across four engines and four control mechanisms. Testing Strategy v2 §11 names
the one threat that would undo it:

    "Instrument ceiling — a low valence score may reflect the recogniser, not the speech.
     Unaddressed, it invalidates the central claim."

A low valence score has two possible causes and the project currently cannot distinguish
them: either the speech does not carry valence, or **the recogniser cannot hear it**. The
distinction is not a detail — it decides whether Chapter 6 reports a finding about speech
synthesis or a finding about speech emotion recognition. Both are publishable; claiming the
wrong one is not.

The test is simple and the data is already on disk. RAVDESS is **acted, labelled, studio-
recorded human emotional speech** — as close to a ceiling as this instrument will ever see.
If the recogniser scores valence at chance on RAVDESS, then valence at chance on ECHO's
clips says nothing about ECHO. If it scores valence well on RAVDESS and poorly on ECHO,
the finding is about the synthesis.

    M1 — dimensional SER over labelled RAVDESS  -> the recogniser's ceiling
    M2 — UTMOS over natural human recordings    -> the naturalness scale's ceiling

M2 anchors every mean-opinion-score figure in the thesis. "Kokoro scores 4.51" is
uninterpretable until it is known what *natural human speech* scores on the same predictor;
the expected range is roughly 4.3-4.7, and a natural anchor below the engines would
invalidate the naturalness ranking outright.

Method note — this run is itself an instance of the categorical->dimensional mapping problem
--------------------------------------------------------------------------------------------
RAVDESS labels are **categorical** (happy, angry, sad, calm); ECHO's targets are
**dimensional** quadrants. Assigning happy->Q1 is a mapping, not a fact, and the project's
own protocol requires it to be declared rather than assumed. The mapping used here is the
same one `make_ravdess_refs.py` uses for the reference clips, so the ceiling is measured
under exactly the assumption the rest of the project already operates under. Where the
recogniser disagrees with a label, that is reported as displacement rather than as error.

    python check_instruments.py --ravdess RAVDESS --per-quadrant 20
    python check_instruments.py --skip-utmos          # M1 only, faster

Results are timestamped and never overwritten.
"""

from __future__ import annotations

import argparse
import random
import time
from collections import Counter
from pathlib import Path

from make_ravdess_refs import QUADRANT_EMOTION

QUADRANTS = ("Q1", "Q2", "Q3", "Q4")
#: RAVDESS emotion code -> quadrant, inverted from the reference-builder's mapping so the
#: ceiling is measured under the same declared assumption the reference clips use.
EMOTION_QUADRANT = {code: q for q, (code, _label) in QUADRANT_EMOTION.items()}
EMOTION_LABEL = {code: label for _q, (code, label) in QUADRANT_EMOTION.items()}


#: RAVDESS emotion code 01 = neutral. Excluded from M1 (it has no quadrant, and assigning
#: one would be an unjustified mapping) but REQUIRED for M2 — see `natural_anchor_pool`.
NEUTRAL_CODE = "01"


def parse_ravdess(path: Path, allow_neutral: bool = False) -> "dict | None":
    """Decode a RAVDESS filename into its fields, or None if it does not parse.

    modality-vocalChannel-emotion-intensity-statement-repetition-actor
    """
    parts = path.stem.split("-")
    if len(parts) != 7:
        return None
    modality, channel, emotion, intensity, statement, repetition, actor = parts
    if modality != "03" or channel != "01":          # audio-only speech
        return None
    if emotion == NEUTRAL_CODE and allow_neutral:
        return {"path": path, "emotion": emotion, "label": "neutral", "quadrant": "",
                "intensity": intensity, "statement": statement, "actor": int(actor)}
    if emotion not in EMOTION_QUADRANT:              # only the four mapped emotions
        return None
    return {"path": path, "emotion": emotion, "label": EMOTION_LABEL[emotion],
            "quadrant": EMOTION_QUADRANT[emotion], "intensity": intensity,
            "statement": statement, "actor": int(actor)}


def natural_anchor_pool(root: Path, n: int, seed: int) -> list[dict]:
    """NEUTRAL human clips — the correct anchor for a naturalness predictor.

    Corrects a methodological error in the first run of this script (2026-08-31), which
    scored UTMOS over the *emotional* sample and reported 3.353 for "natural human speech" —
    below five of ECHO's seven engine configurations, which would have invalidated the
    naturalness scale.

    **Naturalness is not emotion.** UTMOS predicts mean opinion score for synthesis
    naturalness, and its training material is overwhelmingly ordinary read speech. Shouted
    anger and whispered sadness are atypical *as speech*, so scoring them and calling the
    result "the natural anchor" measures the emotion, not the naturalness ceiling. RAVDESS
    emotion code 01 (neutral) is the material that belongs in that role.

    The emotional pool is still scored, separately — see §M2b. The difference between the
    two is itself a result.
    """
    clips = [c for c in (parse_ravdess(p, allow_neutral=True)
                         for p in sorted(root.rglob("*.wav"))) if c]
    neutral = [c for c in clips if c["emotion"] == NEUTRAL_CODE]
    by_actor: dict[int, list[dict]] = {}
    for c in neutral:
        by_actor.setdefault(c["actor"], []).append(c)
    rng = random.Random(seed)
    for lst in by_actor.values():
        rng.shuffle(lst)
    picked, actors = [], sorted(by_actor)
    while len(picked) < n and any(by_actor[a] for a in actors):
        for a in actors:
            if by_actor[a] and len(picked) < n:
                picked.append(by_actor[a].pop())
    return picked


def sample_balanced(root: Path, per_quadrant: int, seed: int) -> list[dict]:
    """A balanced, seeded sample: equal per quadrant, spread across actors.

    Spreading across actors matters more than sample size here. RAVDESS has 24 actors and
    a recogniser's apparent accuracy can be carried by a handful of expressive performers,
    so a sample concentrated in a few actors would measure those actors rather than the
    instrument. Sorting by actor before the round-robin makes the spread deterministic.
    """
    clips = [c for c in (parse_ravdess(p) for p in sorted(root.rglob("*.wav"))) if c]
    rng = random.Random(seed)
    out: list[dict] = []
    for q in QUADRANTS:
        pool = [c for c in clips if c["quadrant"] == q]
        by_actor: dict[int, list[dict]] = {}
        for c in pool:
            by_actor.setdefault(c["actor"], []).append(c)
        for lst in by_actor.values():
            rng.shuffle(lst)
        picked, actors = [], sorted(by_actor)
        while len(picked) < per_quadrant and any(by_actor[a] for a in actors):
            for a in actors:                          # round-robin over actors
                if by_actor[a] and len(picked) < per_quadrant:
                    picked.append(by_actor[a].pop())
        out.extend(picked)
    return out


def confusion(pairs: "list[tuple[str, str]]") -> str:
    """Target x recognised table. Rows are the RAVDESS label, columns the recogniser."""
    counts = Counter(pairs)
    lines = ["    " + "".join(f"{q:>7}" for q in QUADRANTS) + "     n   acc"]
    for t in QUADRANTS:
        row = [counts[(t, r)] for r in QUADRANTS]
        n = sum(row)
        acc = (counts[(t, t)] / n * 100) if n else 0.0
        lines.append(f"  {t} " + "".join(f"{v:>7}" for v in row) + f"{n:>6}{acc:>6.0f}%")
    return "\n".join(lines)


def mean_ci(values: "list[float]") -> "tuple[float, float, float]":
    """Mean with a 95 % normal-approximation interval."""
    n = len(values)
    if n == 0:
        return float("nan"), float("nan"), float("nan")
    m = sum(values) / n
    if n < 2:
        return m, float("nan"), float("nan")
    var = sum((v - m) ** 2 for v in values) / (n - 1)
    half = 1.96 * (var ** 0.5) / (n ** 0.5)
    return m, m - half, m + half


def main(argv: "list[str] | None" = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ravdess", default="RAVDESS", help="extracted RAVDESS speech folder")
    ap.add_argument("--per-quadrant", type=int, default=20,
                    help="clips per quadrant (80 total at the default)")
    ap.add_argument("--seed", type=int, default=666, help="sampling seed, recorded")
    ap.add_argument("--skip-utmos", action="store_true", help="M1 only")
    ap.add_argument("--out", default="research/instrument_ceilings",
                    help="results folder (timestamped, never overwritten)")
    args = ap.parse_args(argv)

    root = Path(args.ravdess)
    if not root.is_dir():
        print(f"RAVDESS folder not found: {root}")
        print("Fix: point --ravdess at the extracted Audio_Speech_Actors_01-24 folder.")
        return 1

    print("Instrument ceilings — what the objective instruments score on real human speech")
    print("=" * 78)
    clips = sample_balanced(root, args.per_quadrant, args.seed)
    if not clips:
        print(f"No usable RAVDESS clips under {root}.")
        return 1
    actors = sorted({c["actor"] for c in clips})
    print(f"\nSample: {len(clips)} clips · {args.per_quadrant} per quadrant · "
          f"{len(actors)} actors · seed {args.seed}")
    print("Mapping (declared, same as make_ravdess_refs.py): "
          + " · ".join(f"{q}<-{EMOTION_LABEL[c]}" for q, (c, _l) in QUADRANT_EMOTION.items()))

    # --- M1: the recogniser's ceiling ------------------------------------
    print("\n" + "-" * 78)
    print("M1 — dimensional SER over labelled human speech")
    print("-" * 78)
    try:
        from emotion_conveyance import predict_va, quadrant_of
    except Exception as exc:
        print(f"  Could not import the recogniser: {exc}")
        return 1

    rows = []
    for i, c in enumerate(clips, 1):
        try:
            rec = predict_va(c["path"])
        except Exception as exc:
            print(f"  [{i}/{len(clips)}] FAILED {c['path'].name}: {exc}")
            continue
        v, a = rec["rec_valence"], rec["rec_arousal"]
        rows.append({**c, "v": v, "a": a, "rec_q": quadrant_of(v, a)})
        if i % 10 == 0 or i == len(clips):
            print(f"  [{i}/{len(clips)}] scored", flush=True)
    if not rows:
        print("  No clips scored.")
        return 1

    quad_acc = sum(r["rec_q"] == r["quadrant"] for r in rows) / len(rows)
    # Sign accuracy on each axis, against the quadrant anchors the contract defines.
    from contracts import Quadrant, anchor_for

    aro_hits = val_hits = 0
    for r in rows:
        tv, ta = anchor_for(Quadrant(r["quadrant"]))
        aro_hits += (r["a"] >= 0) == (ta >= 0)
        val_hits += (r["v"] >= 0) == (tv >= 0)
    aro_acc, val_acc = aro_hits / len(rows), val_hits / len(rows)

    print(f"\n  Quadrant accuracy   {quad_acc*100:5.1f}%   (chance 25%)")
    print(f"  Arousal sign        {aro_acc*100:5.1f}%   (chance 50%)")
    print(f"  Valence sign        {val_acc*100:5.1f}%   (chance 50%)")
    print("\n  Confusion — rows = RAVDESS label, columns = recognised\n")
    print(confusion([(r["quadrant"], r["rec_q"]) for r in rows]))

    print("\n  THE CEILING, AND HOW TO READ ECHO'S NUMBERS AGAINST IT:")
    if val_acc < 0.60:
        print("  * Valence is at or near chance ON ACTED HUMAN SPEECH. The recogniser cannot")
        print("    reliably hear valence in material far more expressive than any synthesiser")
        print("    produces. ECHO's valence result is therefore BOUNDED BY THE INSTRUMENT and")
        print("    must NOT be reported as a property of the synthesised speech.")
    else:
        print(f"  * Valence reaches {val_acc*100:.0f}% on acted human speech, so the recogniser")
        print("    CAN hear valence when it is present. ECHO's valence result is therefore")
        print("    attributable to the synthesis rather than to the instrument.")
    print(f"  * Arousal at {aro_acc*100:.0f}% is the practical upper bound for any ECHO arousal figure.")

    # --- M2: the naturalness anchor --------------------------------------
    mos_line = "skipped"
    mos_by_clip: dict = {}
    if not args.skip_utmos:
        print("\n" + "-" * 78)
        print("M2 — UTMOS: the naturalness anchor, on NEUTRAL human speech")
        print("-" * 78)
        try:
            from naturalness import predict_mos

            neutral = natural_anchor_pool(root, args.per_quadrant, args.seed)
            print(f"  Anchor pool: {len(neutral)} NEUTRAL clips "
                  f"({len({c['actor'] for c in neutral})} actors).")
            print("  Neutral, not emotional: UTMOS scores naturalness, and shouted anger or")
            print("  whispered sadness is atypical AS SPEECH. Scoring those and calling the")
            print("  result 'the natural anchor' would measure the emotion, not the ceiling.")

            def score(pool, tag):
                vals = []
                for i, r in enumerate(pool, 1):
                    try:
                        s = predict_mos(r["path"])
                        vals.append(s)
                        mos_by_clip[r["path"].name] = s
                    except Exception:
                        pass
                    if i % 20 == 0 or i == len(pool):
                        print(f"  [{tag} {i}/{len(pool)}] scored", flush=True)
                return vals

            neu = score(neutral, "neutral")
            if neu:
                m, lo, hi = mean_ci(neu)
                mos_line = f"{m:.3f} [{lo:.3f}, {hi:.3f}] over {len(neu)} neutral clips"
                print(f"\n  NATURAL ANCHOR (neutral human speech): UTMOS {mos_line}")
                print("  Expected ~4.3-4.7. Every engine MOS in the thesis is read against THIS.")
                if m < 4.0:
                    print("  WARNING: still below 4.0 on neutral studio speech. The anchor itself")
                    print("  is suspect — investigate before interpreting any engine ranking.")

            # --- M2b: what emotion costs, measured on HUMAN speech ---------
            print("\n" + "-" * 78)
            print("M2b — the same predictor on EMOTIONAL human speech (the control)")
            print("-" * 78)
            emo = score(rows, "emotional")
            if neu and emo:
                mn, _, _ = mean_ci(neu)
                me, elo, ehi = mean_ci(emo)
                print(f"\n  neutral human   {mn:.3f}")
                print(f"  emotional human {me:.3f} [{elo:.3f}, {ehi:.3f}]")
                print(f"  difference      {me - mn:+.3f}")
                print("\n  WHY THIS IS A CONTROL, NOT A CURIOSITY:")
                print("  ECHO measured a within-engine expressivity cost — naturalness declines")
                print("  monotonically as emotional dials are added. If emotional HUMAN speech")
                print("  also scores below neutral human speech on the same predictor, that cost")
                print("  is not an artefact of synthesis: it is a property of emotional speech,")
                print("  of the predictor, or of both — and ECHO's engines are being penalised")
                print("  for doing exactly what they were asked to do.")
        except Exception as exc:
            print(f"  UTMOS unavailable ({exc}) — rerun with the eval extras installed.")

    # --- persist ----------------------------------------------------------
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    import csv

    csv_path = out_dir / f"{stamp}_ceilings_n{len(rows)}.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["file", "actor", "label", "target_quadrant", "intensity",
                    "rec_valence", "rec_arousal", "rec_quadrant", "utmos"])
        for r in rows:
            mos = mos_by_clip.get(r["path"].name)
            w.writerow([r["path"].name, r["actor"], r["label"], r["quadrant"],
                        r["intensity"], f"{r['v']:.4f}", f"{r['a']:.4f}", r["rec_q"],
                        f"{mos:.4f}" if mos is not None else ""])

    txt_path = out_dir / f"{stamp}_ceilings_n{len(rows)}.txt"
    txt_path.write_text(
        f"Instrument ceilings — {stamp}\n"
        f"sample: {len(rows)} clips, {args.per_quadrant}/quadrant, "
        f"{len(actors)} actors, seed {args.seed}\n"
        f"mapping: happy->Q1 angry->Q2 sad->Q3 calm->Q4 (declared, per make_ravdess_refs.py)\n\n"
        f"M1 quadrant {quad_acc*100:.1f}%  arousal {aro_acc*100:.1f}%  valence {val_acc*100:.1f}%\n"
        f"M2 UTMOS natural anchor: {mos_line}\n\n"
        + confusion([(r["quadrant"], r["rec_q"]) for r in rows]) + "\n",
        encoding="utf-8")

    print(f"\nWritten (never overwritten):\n  {csv_path}\n  {txt_path}")
    print("\nBoth figures belong beside every ECHO number they bound — Chapter 5 tables and")
    print("the Chapter 6 discussion of what the instruments can and cannot see.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
