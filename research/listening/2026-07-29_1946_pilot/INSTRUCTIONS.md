# Listening test — instructions

24 clips, blinded and in random order. Every clip speaks the SAME neutral sentence set,
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
   - `Q1` = happy / excited   (positive, high energy)
   - `Q2` = upset / agitated   (negative, high energy)
   - `Q3` = sad / subdued   (negative, low energy)
   - `Q4` = calm / content   (positive, low energy)
   You must choose one even if unsure (forced choice) — guessing is part of the design.

3. `notes` — optional free text (e.g. "robotic", "flat", "clipped").

## After finishing
    python make_listening_test.py --score --session <this folder>
