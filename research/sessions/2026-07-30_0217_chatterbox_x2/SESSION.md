# Generation session — 2026-07-30_0217_chatterbox_x2

- **Created (UTC):** 2026-07-30T01:36:10.486858+00:00
- **Purpose / objective:** X2 native emotion conditioning: exaggeration-only (no reference clips)
- **Engine:** `chatterbox`
- **Engine settings:** `refs=(none)`, `device=cpu`
- **Settings provenance:** BACKFILLED 2026-09-01 — NOT recorded at render time. `synth_stimuli.py` began writing the engine-settings line on 2026-08-31, so sessions before that date carry none, and `build_scorecard.py` could not show the engine x reference-level contrast for them. Basis: Purpose line of this file states "exaggeration-only (no reference clips)" — Condition A, the no-valence-channel baseline. Reconstructed, never observed — read it as such.
- **Parameter sets:** rate_volume_pitch
- **Git commit:** `5e7d99b`   **nearest tag:** `v0.4-naturalness2`
- **Stimuli:** 5 fixed neutral sentences (S01, S02, S03, S04, S05)
- **Quadrants:** Q1–Q4   ·   **Clips:** 20   ·   **flagged out-of-band [2.5–15.0 s]:** 0

## What to compare
- **Before vs After (clearest):** `neutral/<clip>` (flat, emotionless voice) vs `rate_volume_pitch/<clip>` for the SAME file, e.g. `S01_Q1.wav` -> the voice goes from neutral to expressive. (`neutral/` sounds identical across quadrants -- that is the point.)
- **Emotion distinction:** within `rate_volume_pitch/`, compare `S01_Q1` (happy) vs `S01_Q3` (sad).
- **Ablation (per-dial, subtle):** `rate/` -> `rate_volume/` -> `rate_volume_pitch/` isolates each dial's marginal effect. This is the research view, NOT the demo (differences here are small).
- Against other sessions/engines at the same or a different **tag** (the evolution).

## Files
- `register.csv` — one row per clip (dials, stimulus, target, SHA-256, duration_ok).
- `audio/<engine>/<param_set>/<stimulus>_<quadrant>.wav` — clips share a name across param-set folders for trivial A/B (git-ignored; back up separately).
