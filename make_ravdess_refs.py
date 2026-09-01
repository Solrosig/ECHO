"""Build per-quadrant reference clips from RAVDESS (Condition C).

Condition B used self-recorded references and produced the best emotion conveyance in the study
(arousal 100 %) but a naturalness drop (4.34 -> 3.37), because Chatterbox clones the REFERENCE
speaker — so consumer-microphone quality was inherited. Condition C repeats the experiment with
professionally recorded references (RAVDESS: studio recordings, trained actors, labelled
emotion) to test whether that drop was a reference-quality artefact rather than a cost of the
method. Same actor for all four clips, so voice identity is held constant across quadrants.

RAVDESS filename: modality-vocalChannel-emotion-intensity-statement-repetition-actor.wav
  modality 03 = audio-only · vocalChannel 01 = speech
  emotion  01 neutral · 02 calm · 03 happy · 04 sad · 05 angry · 06 fearful · 07 disgust · 08 surprised
  intensity 01 normal · 02 strong · actor 01-24 (odd = male, even = female)

ECHO quadrant mapping (Russell valence-arousal):
  Q1 happy/excited   <- 03 happy   (positive valence, high arousal)
  Q2 upset/agitated  <- 05 angry   (negative valence, high arousal)
  Q3 sad/subdued     <- 04 sad     (negative valence, low arousal)
  Q4 calm/content    <- 02 calm    (positive valence, low arousal)  [RAVDESS has an explicit
                                    'calm' class, which fits Q4 far better than 'neutral']

    python make_ravdess_refs.py --ravdess C:\\path\\to\\Audio_Speech_Actors_01-24 --actor 1
        -> refs_ravdess/Q1.wav .. Q4.wav   (then: python check_refs.py --dir refs_ravdess)

Refs: Livingstone & Russo (2018), PLoS ONE 13(5), e0196391 (CC BY-NC-SA 4.0 — research use).
"""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

# quadrant -> (RAVDESS emotion code, human label)
QUADRANT_EMOTION = {
    "Q1": ("03", "happy"),
    "Q2": ("05", "angry"),
    "Q3": ("04", "sad"),
    "Q4": ("02", "calm"),
}

#: RAVDESS actors speak exactly two carrier sentences, identified by the 5th filename field.
#: The words are held constant across emotions BY DESIGN — which is what makes the corpus a
#: clean emotion manipulation, and what lets the transcript be read off the filename.
RAVDESS_STATEMENTS = {
    "01": "Kids are talking by the door.",
    "02": "Dogs are sitting by the door.",
}


def statement_text(filename: str) -> "str | None":
    """Transcript of a RAVDESS clip, from the statement code in its filename.

    ZipVoice is zero-shot: it clones from `--prompt-wav` AND `--prompt-text`, and has no
    default voice to fall back on, so a reference clip without its transcript is unusable.
    Chatterbox never needed this (it takes audio alone), which is why the transcript is
    only being written now.

    Returns None for a name that does not parse, so a malformed file is reported rather
    than silently paired with the wrong sentence — the transcript must match the audio or
    the clone is conditioned on a lie.
    """
    parts = Path(filename).stem.split("-")
    if len(parts) != 7:
        return None
    return RAVDESS_STATEMENTS.get(parts[4])


def find_clip(root: Path, emotion: str, actor: int, intensity: str, statement: str) -> "Path | None":
    """Locate one RAVDESS clip, relaxing intensity then statement if the exact match is absent.

    'neutral' and sometimes 'calm' are recorded at normal intensity only, so an exact
    intensity match cannot be required for every emotion."""
    actor_s = f"{actor:02d}"
    patterns = [
        f"03-01-{emotion}-{intensity}-{statement}-*-{actor_s}.wav",   # exact
        f"03-01-{emotion}-{intensity}-*-*-{actor_s}.wav",             # any statement
        f"03-01-{emotion}-*-*-*-{actor_s}.wav",                       # any intensity
    ]
    for pat in patterns:
        hits = sorted(root.rglob(pat))
        if hits:
            return hits[0]
    return None


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--ravdess", required=True, help="extracted RAVDESS speech folder")
    ap.add_argument("--actor", type=int, default=1, help="actor 1-24 (odd male, even female)")
    ap.add_argument("--out", default="refs_ravdess", help="output reference folder")
    ap.add_argument("--intensity", default="02", choices=["01", "02"], help="01 normal, 02 strong")
    ap.add_argument("--statement", default="01", choices=["01", "02"])
    args = ap.parse_args(argv)

    root = Path(args.ravdess)
    if not root.exists():
        print(f"RAVDESS folder not found: {root}")
        return 1
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    print(f"Actor {args.actor:02d} ({'male' if args.actor % 2 else 'female'}), "
          f"intensity {'strong' if args.intensity == '02' else 'normal'} — one speaker for all "
          f"four quadrants, so voice identity is constant.\n")
    missing = 0
    for q, (emo, label) in QUADRANT_EMOTION.items():
        src = find_clip(root, emo, args.actor, args.intensity, args.statement)
        if src is None:
            print(f"  {q}  <- {label:<6} MISSING (no file for emotion {emo}, actor {args.actor:02d})")
            missing += 1
            continue
        dst = out / f"{q}.wav"
        shutil.copyfile(src, dst)
        # Transcript sidecar, required by zero-shot engines (ZipVoice) that clone from
        # audio + text. Read from the ACTUAL file selected, not from --statement, because
        # find_clip() relaxes the statement constraint when an exact match is unavailable —
        # so assuming the requested sentence would sometimes write the wrong words.
        text = statement_text(src.name)
        if text is None:
            print(f"  {q}  <- {label:<6} {src.name}  (WARNING: unparseable name, no transcript)")
            missing += 1
            continue
        (out / f"{q}.txt").write_text(text, encoding="utf-8")
        print(f"  {q}  <- {label:<6} {src.name}   \"{text}\"")

    if missing:
        print(f"\n{missing} quadrant(s) unmatched — check the folder path and actor number.")
        return 1
    print(f"\nWrote 4 reference clips + 4 transcripts to {out}. Next:")
    print(f"  python check_refs.py --dir {out}")
    print(f"  set ECHO_CHATTERBOX_REFS={out}          (Chatterbox: audio only)")
    print(f"  set ECHO_ZIPVOICE_REFS={out}            (ZipVoice: audio + transcript)")
    print("  python synth_stimuli.py --engine chatterbox --param-set rate_volume_pitch "
          "--label chatterbox_x2_ravdess --purpose \"X2 condition C: professional RAVDESS references\"")
    print("  python synth_stimuli.py --engine zipvoice --param-set rate_volume_pitch "
          "--label zipvoice_b4_ravdess --purpose \"B4: ZipVoice on the same references — "
          "mechanism vs engine\"")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
