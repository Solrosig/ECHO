# ECHO — build guide for Claude Code

The MVP is an **open-source, local, command-line** demo: one message + one target emotion →
emotion-conditioned reply → audible speech → one fully logged turn. **No UI.**

## Protected seams (do not change casually — review any diff that touches these)
1. **EmotionContract** (`contracts.py`) — the single data structure carried through the whole pipeline.
2. **Adapter interfaces** (`adapters/llm.py`, `adapters/tts.py`) — `LLMAdapter`, `TTSAdapter` ABCs.
   Later phases add a commercial adapter as a new class, never by editing the pipeline.
3. **Provenance schema** (`persistence.py`) — one row per turn + one row per attempt.

## Architectural rule (do not break)
Three concerns stay separated behind stable interfaces:
- **control**: `contracts`, `strategies`, `prompts/`
- **generation**: `adapters/`, `orchestrator`, `gate`
- **persistence**: `persistence`

The orchestrator/adapters generate; nothing reads model state for analysis except by reading the log.
Every swappable factor (`EncodingStrategy`, `LLMAdapter`, `TTSAdapter`) is an ABC with concrete
implementations, so later phases add a class instead of editing the pipeline.

## Conventions
- One epic per branch (`feat/e1-contract`); one commit per story.
- Write the test in the same story as the code. Mock the LLM/TTS at the adapter boundary;
  never assert on model-generated content.
- Keep `main` green. Templates and mappings live as data, not literals in code.

## Run
```
pip install -e ".[dev]"
pytest -m "not slow"          # fast unit tests, no external tools
echo-run "I lost my keys again" --all-quadrants
```
