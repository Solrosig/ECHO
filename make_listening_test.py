"""Blinded listening test — pilot kit (Story S1.0), and the seed of the full S1 study.

Human ears are the ground truth for naturalness and emotion; this builds a small, BLINDED,
randomised listening set so even a single-listener pass is evidence rather than impression
(blinding removes experimenter-expectancy bias), and scores it with the same two measures the
machine used, so human and machine are directly comparable:
  * naturalness MOS 1-5   (ITU-T P.800 absolute category rating)  <-> UTMOS (N4)
  * 4-AFC emotion identification (which quadrant?) + confusion     <-> dimensional SER (N5)

    python make_listening_test.py --build --per-engine 8
        -> research/listening/<stamp>_pilot/clips/001.wav ...   (opaque IDs, random order)
        -> answers.csv   (blank: you fill naturalness + emotion)
        -> key.csv       (unblinding key — do NOT open before listening)

    python make_listening_test.py --score --session research/listening/<stamp>_pilot
        -> mean MOS per engine, 4-AFC accuracy, and the confusion matrix

Design mirrors S1 at small scale so the protocol and code carry forward: balanced across
engines x quadrants, full-dial param-set (where all three dials are active), fixed carrier
text (so only the voice varies).
"""

from __future__ import annotations

import argparse
import csv
import random
import shutil
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from statistics import mean

QUADRANTS = ["Q1", "Q2", "Q3", "Q4"]
LABELS = {"Q1": "happy / excited", "Q2": "upset / agitated",
          "Q3": "sad / subdued", "Q4": "calm / content"}


def build(register: Path, out_root: Path, per_engine: int, param_set: str, seed: int) -> int:
    rows = [r for r in csv.DictReader(open(register, encoding="utf-8"))
            if r.get("silent") != "yes" and r.get("param_set") == param_set
            and Path(r.get("audio_path", "")).exists()]
    if not rows:
        print(f"No usable clips in {register} for param-set '{param_set}'.")
        return 1

    rng = random.Random(seed)                     # seeded -> the sample is reproducible
    by_engine: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        by_engine[r.get("engine", "?")].append(r)

    picked: list[dict] = []
    for eng, clips in sorted(by_engine.items()):
        per_quad: dict[str, list[dict]] = defaultdict(list)
        for c in clips:
            per_quad[c.get("quadrant", "?")].append(c)
        n_each = max(1, per_engine // len(QUADRANTS))          # balance across quadrants
        for q in QUADRANTS:
            pool = per_quad.get(q, [])
            picked.extend(rng.sample(pool, min(n_each, len(pool))))

    rng.shuffle(picked)                            # randomise presentation order
    stamp = datetime.now().strftime("%Y-%m-%d_%H%M")
    session = out_root / f"{stamp}_pilot"
    (session / "clips").mkdir(parents=True, exist_ok=True)

    key_rows, ans_rows = [], []
    for i, r in enumerate(picked, start=1):
        blind = f"{i:03d}"
        shutil.copyfile(r["audio_path"], session / "clips" / f"{blind}.wav")
        key_rows.append({"blind_id": blind, "engine": r.get("engine", ""),
                         "quadrant": r.get("quadrant", ""), "stimulus_id": r.get("stimulus_id", ""),
                         "param_set": r.get("param_set", ""), "source_path": r["audio_path"]})
        ans_rows.append({"blind_id": blind, "naturalness_1to5": "", "emotion_guess": "", "notes": ""})

    with open(session / "key.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(key_rows[0].keys()))
        w.writeheader()
        w.writerows(key_rows)
    with open(session / "answers.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["blind_id", "naturalness_1to5", "emotion_guess", "notes"])
        w.writeheader()
        w.writerows(ans_rows)
    (session / "INSTRUCTIONS.md").write_text(_instructions(len(picked)), encoding="utf-8")

    print(f"Listening test built: {session}")
    print(f"  {len(picked)} clips ({', '.join(sorted(by_engine))}), blinded + randomised (seed {seed})")
    print(f"  fill in: {session / 'answers.csv'}   ·   do NOT open key.csv until finished")
    print(f"  read:    {session / 'INSTRUCTIONS.md'}")
    return 0


def _instructions(n: int) -> str:
    return f"""# Listening test — instructions

{n} clips, blinded and in random order. Every clip speaks the SAME neutral sentence set,
so only the VOICE differs. Do not open `key.csv` until you have finished.

## Setup
- Quiet room, headphones, fixed comfortable volume. **Do not change the volume during the test**
  (loudness is one of the things being judged).

## For each clip `clips/001.wav`, `002.wav`, … record two answers in `answers.csv`

1. **naturalness_1to5** — how natural/human does the voice sound? (ITU-T P.800 scale)
   5 = excellent (indistinguishable from a human recording) · 4 = good · 3 = fair ·
   2 = poor · 1 = bad (clearly machine-like)
   Judge the VOICE QUALITY only, not the emotion and not the words.

2. **emotion_guess** — which emotion is this voice expressing? Answer exactly `Q1`, `Q2`, `Q3` or `Q4`:
   - `Q1` = {LABELS['Q1']}   (positive, high energy)
   - `Q2` = {LABELS['Q2']}   (negative, high energy)
   - `Q3` = {LABELS['Q3']}   (negative, low energy)
   - `Q4` = {LABELS['Q4']}   (positive, low energy)
   You must choose one even if unsure (forced choice) — guessing is part of the design.

3. `notes` — optional free text (e.g. "robotic", "flat", "clipped").

## After finishing
    python make_listening_test.py --score --session <this folder>
"""


def _norm_id(bid: str) -> str:
    """Normalise a blind id. Excel silently strips leading zeros when it saves a CSV, turning
    '001' into '1' — which would break the join with key.csv and yield an empty (misleading)
    result table. Zero-pad numeric ids on BOTH sides so listener sheets round-trip through
    Excel, Sheets or a text editor alike."""
    b = (bid or "").strip()
    return b.zfill(3) if b.isdigit() else b


def score(session: Path) -> int:
    key = {_norm_id(r["blind_id"]): r
           for r in csv.DictReader(open(session / "key.csv", encoding="utf-8"))}
    answers = [r for r in csv.DictReader(open(session / "answers.csv", encoding="utf-8"))
               if (r.get("naturalness_1to5") or "").strip() or (r.get("emotion_guess") or "").strip()]
    if not answers:
        print(f"No answers filled in yet: {session / 'answers.csv'}")
        return 1

    mos: dict[str, list[float]] = defaultdict(list)
    conf: dict[str, dict[tuple[str, str], int]] = defaultdict(lambda: defaultdict(int))
    hits: dict[str, list[int]] = defaultdict(list)
    unmatched = 0
    for a in answers:
        k = key.get(_norm_id(a.get("blind_id", "")))
        if not k:
            unmatched += 1
            continue
        eng = k["engine"]
        try:
            mos[eng].append(float(a["naturalness_1to5"]))
        except (TypeError, ValueError):
            pass
        guess = (a.get("emotion_guess") or "").strip().upper()
        if guess in QUADRANTS:
            conf[eng][(k["quadrant"], guess)] += 1
            hits[eng].append(1 if guess == k["quadrant"] else 0)

    if unmatched:
        print(f"\nWARNING: {unmatched} answer row(s) had a blind_id not present in key.csv "
              "— check the id column was not altered when saving.")
    if not mos and not hits:
        print("\nNo answers could be scored: the ids matched none in key.csv, or the "
              "naturalness/emotion columns are empty or non-numeric.")
        return 1
    print(f"\n== Listening test results — {session.name} ({len(answers)} clips rated) ==")
    print(f"  {'engine':<12}{'mean MOS':>10}{'n':>4}{'4-AFC emotion acc':>20}{'n':>4}")
    for eng in sorted(set(list(mos) + list(hits))):
        m = f"{mean(mos[eng]):10.2f}" if mos.get(eng) else f"{'-':>10}"
        h = f"{mean(hits[eng]):19.0%}" if hits.get(eng) else f"{'-':>19}"
        print(f"  {eng:<12}{m}{len(mos.get(eng, [])):4d}{h}{len(hits.get(eng, [])):5d}")
    print("  (4-AFC chance = 25 %)")

    for eng in sorted(conf):
        print(f"\n  Confusion — {eng} (rows = intended, cols = perceived)")
        print("       " + "".join(f"{q:>6}" for q in QUADRANTS))
        for qi in QUADRANTS:
            print(f"    {qi:<5}" + "".join(f"{conf[eng].get((qi, qj), 0):>6}" for qj in QUADRANTS))
    print("\nCompare with the machine scores: UTMOS (research/naturalness.csv) and SER "
          "(research/emotion.csv). Agreement = convergent validity; disagreement is itself a finding.")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--build", action="store_true", help="create a blinded listening set")
    ap.add_argument("--score", action="store_true", help="score a completed answers.csv")
    ap.add_argument("--register", default="research/register.csv")
    ap.add_argument("--out-root", default="research/listening")
    ap.add_argument("--session", default=None, help="session folder (for --score)")
    ap.add_argument("--per-engine", type=int, default=8, help="clips per engine (balanced over Q1-Q4)")
    ap.add_argument("--param-set", default="rate_volume_pitch")
    ap.add_argument("--seed", type=int, default=20260727, help="seed -> reproducible sample")
    args = ap.parse_args(argv)

    if args.build:
        reg = Path(args.register)
        if not reg.exists():
            print(f"Register not found: {reg} (run build_register.py --build first).")
            return 1
        return build(reg, Path(args.out_root), args.per_engine, args.param_set, args.seed)
    if args.score:
        if not args.session:
            print("--score needs --session <folder>")
            return 1
        return score(Path(args.session))
    ap.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
