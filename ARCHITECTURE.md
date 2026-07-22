# ECHO — build guide

The MVP is an **open-source, local, command-line** demo: one message + one target emotion →
emotion-conditioned reply → audible speech → one fully logged turn. **No UI.**
Built as **plain standalone scripts** in one folder (no package wrapper).

## Protected seams (do not change casually — review any diff that touches these)
1. **EmotionContract** (`contracts.py`) — the single data structure carried through the pipeline.
2. **Adapter interfaces** (`llm.py`, `tts.py`) — `LLMAdapter`, `TTSAdapter` ABCs.
   Later phases add a commercial adapter as a new class, never by editing the pipeline.
3. **Provenance schema** (`persistence.py`) — one row per turn + one row per attempt.

## Architectural rule (do not break)
Three concerns stay separated behind stable interfaces:
- **control**: `contracts.py`, `strategies.py`, `prompts/`
- **generation**: `llm.py`, `tts.py`, `orchestrator.py`, `gate.py`
- **persistence**: `persistence.py`

The orchestrator/adapters generate; nothing reads model state for analysis except by reading
the log. Every swappable factor (`EncodingStrategy`, `LLMAdapter`, `TTSAdapter`) is an ABC with
concrete implementations, so later phases add a class instead of editing the pipeline.

## Voice control
The strategy maps the emotion to three engine-agnostic dials on `VoiceParams`:
- `rate`   ← arousal  (speaking speed)
- `volume` ← arousal  (loudness)
- `pitch`  ← arousal + valence  (voice height; blended so all four quadrants differ)

Engines render what they support: `pyttsx3` and `Kokoro` render rate + volume; the SAPI engine
(`Sapi5XmlAdapter`, selected with `ECHO_TTS_ENGINE=sapi`) also renders **pitch** via SAPI prosody
XML. All engines sit behind the `TTSAdapter` seam and are chosen by config. `rate`, `volume`, and
`pitch` are recorded per turn in the provenance log.

## Conventions
- One commit per script/block. Write the test in the same block as the code.
- Mock the LLM/TTS at the adapter boundary; never assert on model-generated content.
- Keep the working branch green. Templates and mappings live as data, not literals in code.

## Run
```
pip install -r requirements.txt
pytest
python demo.py "I lost my keys again" --all-quadrants
```
