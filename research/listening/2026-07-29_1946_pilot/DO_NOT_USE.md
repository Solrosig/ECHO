# DO NOT USE — `answers.csv` contains no human judgements

Confirmed 2026-09-06: **nobody took this test.** The values in `answers.csv` are placeholder, not data.

Two independent tells, both visible without opening the file:

1. **`INSTRUCTIONS.md`, `answers.csv` and `key.csv` all carry the same mtime — 2026-07-30 00:02:22.**
   `make_listening_test.py --build` writes exactly those three files in one call, so `answers.csv` was
   never edited after creation. A person filling in 24 rows leaves it modified later than the other two.
2. **`naturalness_1to5` takes two values across all 24 rows — 1 and 4.** Never 2, 3 or 5. Per engine it
   resolves to exactly 4.00 for Kokoro and exactly 1.00 for the others: a deterministic function of
   engine, not a human rating.

Everything reported from this folder on 2026-09-06 is **retracted** — see `PROJECT_LOG.md`.

**The folder is kept, never deleted**, so the retraction has something to point at. **Do not reuse it and
do not fill it in now**: build a fresh session instead, per `LISTENING_PRETEST_GUIDE.md`, so there is no
ambiguity about which numbers came from a person.

The `clips/`, `key.csv` and `INSTRUCTIONS.md` in this folder are all sound — only `answers.csv` is empty
of meaning.
