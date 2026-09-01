# Engine runners

Small scripts that ECHO calls **in each engine's own interpreter**.

## Why these exist

StyleTTS 2, CosyVoice 2 and Parler-TTS ship **no command-line interface** — all three are
Python APIs, meant to be imported. ECHO cannot import them: each pins its own torch stack,
and importing any of them into ECHO's process would repeat the dependency conflict that
already forced separate environments for Chatterbox and ZipVoice.

A runner resolves both problems. It lives in ECHO's repository (so it is version-controlled
and reviewable with the rest of the project), and it runs inside the engine's environment
(so the engine's dependencies stay there). ECHO invokes it through the subprocess seam with
the same placeholder contract as any other engine.

**This is also the single place to adjust when an upstream API changes.** Research
repositories move; the adapter, the config and the tests do not have to move with them.

## Contract

Every runner accepts the same arguments and behaves the same way:

| Argument | Meaning |
|---|---|
| `--text` | the sentence to speak |
| `--out` | output WAV path |
| `--seed` | pinned and recorded; stochastic engines must honour it |
| `--instruction` | natural-language emotion instruction (mechanism 5) |
| `--ref-wav` | per-quadrant reference clip (mechanism 3/4) |
| `--model-dir` | local weights, used when the Hugging Face hub is unreachable |

Each writes **one mono WAV** at the model's own sample rate and exits non-zero with an
actionable message on failure. ECHO normalises the container to PCM-16 afterwards, so a
runner need not.
