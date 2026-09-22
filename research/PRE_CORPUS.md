# Pre-corpus sessions — audio that is deliberately outside the analysed corpus

Five session folders under `research/sessions/` contain audio and **no `register.csv`**. They are not a
gap in the corpus; they predate it. This file exists so that nobody — including a future reader of the
audit trail — has to work that out again, or mistake exploration for missing data.

## The folders

| Session | Clips | What it was |
|---|---|---|
| `2026-07-23_0022_smoke` | 60 | first end-to-end synthesis smoke test |
| `2026-07-23_0041_sapi_ab` | 60 | first A/B of SAPI dial settings, before the dials were calibrated |
| `2026-07-23_0920_sapi_v0.2_neutral` | 80 | early `neutral` baseline exploration |
| `2026-07-23_0937_sapi_v0.2_distinct` | 80 | early quadrant-distinctness exploration |
| `2026-07-30_0212_chatterbox_exagg` | 3 | three probe clips while wiring the Chatterbox exaggeration scalar |

## Why they have no register

`synth_stimuli.py` began writing a per-session `register.csv` on **2026-07-26**. Everything rendered before
that date, plus the three Chatterbox probes, was produced by hand or by earlier scripts that recorded
nothing. **The registers were not lost — they were never written.**

## Why they are excluded, and how that is enforced

Every analysis tool in this project iterates `research/sessions/*/register.csv`:
`build_register.py --build`, `build_scorecard.py`, and both scorers read the master register that
`build_register.py` produces. **A folder with no register contributes nothing, by construction.** No
exclusion list is needed and none is maintained — the absence of a register *is* the exclusion, and it
cannot be forgotten or mis-typed.

That is the right outcome on the merits too. These clips have no recorded dials, no quadrant assignment
and no engine settings, so **including them would mean inventing the metadata an analysis needs.** A
reconstructed dial value is a fabricated measurement, and it would be indistinguishable from a real one
once written into a register.

## What they are not excluded from

`backup_audio.py --manifest` walks the **filesystem**, not the registers, so these clips are hashed like
every other. Of the 830 files in the corpus directory, **243 have no matching SHA-256 in any register** —
these five folders, minus the portion of `sapi_v0.2_distinct` whose bytes are byte-identical to clips that
a later session did register. Deterministic engines re-render identical audio, so folder membership and
hash coverage are not the same question, and confusing the two is how the count was first mis-estimated
at 410.

From the manifest onward, corruption in place is detectable here as it is everywhere else. That is the
only guarantee these clips need: they are history, and history should be checkable, not analysed.

## If they were ever wanted

They would need re-rendering under the current harness, not retro-registering. `synth_stimuli.py` with the
same engine and param-set produces a session that is registered, hashed and reproducible from the start —
which is a different and better artefact than a reconstruction of a 2026-07-23 exploration.
