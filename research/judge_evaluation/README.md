# research/judge_evaluation

Transcripts of runs that evaluate the **coherence gate and its judges** — as opposed to
`research/sessions/` (rendered speech corpora) and `research/listening/` (listener-test kits).

Each file is the full terminal output of one `demo.py` run, capturing the reply generated
for every quadrant, which judge decided, whether the gate passed, and how many attempts it
took. The underlying turns are also in `echo.db`, with judge id, judge level, temperature,
prompt version and commit; these transcripts exist so a run can be read without querying
the database.

## Naming

    <date>_judge-<judge>_<model>.txt

## Judges

| Judge | Level | What decides |
|---|---|---|
| `self-report` | L0 | the generating model's own claim — **inoperative under prompts-v2**, which removed the field it reads |
| `blind-llm` | L1 | the same model, fresh context, target withheld |
| `lexicon` | L2 | affective-norm lookup (Warriner et al., 2013); no language model |
| `cascade` | L2 → L1 | lexicon where it has rated vocabulary, blinded LLM where it abstains |

## Runs

| Date | File | Result |
|---|---|---|
| 2026-08-30 | *(A0, transcripts not captured — turns are in `echo.db`)* | self-report 0/4 · blind-llm 4/4 · lexicon 1/4 (placeholder norms) |
| 2026-08-30 | `2026-08-30_judge-cascade_llama3.2-3b.txt` | first run with the published Warriner norms |
