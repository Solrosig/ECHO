# Generation session — 2026-07-26_1733_sapi_e6_realtest

- **Created (UTC):** 2026-07-26T16:33:40.183266+00:00
- **Purpose / objective:** E6 real controllability test
- **Engine:** `sapi5xml`
- **Parameter sets:** neutral, rate, rate_volume, rate_volume_pitch
- **Git commit:** `0061ab2`   **nearest tag:** `v0.2-voice-params`
- **Stimuli:** 5 fixed neutral sentences (S01, S02, S03, S04, S05)
- **Quadrants:** Q1–Q4   ·   **Clips:** 80   ·   **flagged out-of-band [2.5–15.0 s]:** 0

## What to compare
- **Before vs After (clearest):** `neutral/<clip>` (flat, emotionless voice) vs `rate_volume_pitch/<clip>` for the SAME file, e.g. `S01_Q1.wav` -> the voice goes from neutral to expressive. (`neutral/` sounds identical across quadrants -- that is the point.)
- **Emotion distinction:** within `rate_volume_pitch/`, compare `S01_Q1` (happy) vs `S01_Q3` (sad).
- **Ablation (per-dial, subtle):** `rate/` -> `rate_volume/` -> `rate_volume_pitch/` isolates each dial's marginal effect. This is the research view, NOT the demo (differences here are small).
- Against other sessions/engines at the same or a different **tag** (the evolution).

## Files
- `register.csv` — one row per clip (dials, stimulus, target, SHA-256, duration_ok).
- `audio/<engine>/<param_set>/<stimulus>_<quadrant>.wav` — clips share a name across param-set folders for trivial A/B (git-ignored; back up separately).
