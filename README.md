# ECHO — MVP

Emotion-conditioned text **and** speech, in one command. You give ECHO a message and a
target emotion (a quadrant on the valence–arousal plane); it generates a reply in that
emotion, checks the reply actually *sounds* like that emotion, speaks it with a pace and
loudness that reflect the emotion, and logs the whole turn to a database. Open-source,
local, no cloud, no cost.

```
python demo.py "The meeting was moved to a different room" --all-quadrants
```
→ four replies (happy / upset / sad / calm), four spoken clips, four fully-logged turns.

## What it demonstrates (thesis Phase 1)

The project's main risk is the seam between the independent **text** and **speech** channels.
This MVP proves that seam works end to end: one `EmotionContract` flows through generation,
a coherence gate, speech synthesis, and provenance logging — every swappable part
(`EncodingStrategy`, `LLMAdapter`, `TTSAdapter`) sits behind a stable interface so later
phases add a class instead of rewriting the pipeline.

## Quickstart (Windows)

### 1. Install Ollama (the language model)
1. Install from https://ollama.com/download
2. Pull the model: `ollama pull llama3.2:3b`  (Ollama serves at `http://localhost:11434`)

### 2. Install dependencies
```
conda activate echo
pip install -r requirements.txt
```

### 3. Run it
```
python demo.py "The bus was late this morning" --all-quadrants
```
Speech uses the built-in Windows voice (pyttsx3) out of the box — no extra setup.
No external tools handy? Add `--mock` to run the whole pipeline with stubs.

## The four emotions (Russell circumplex quadrants)

| Quadrant | Valence | Arousal | Feels like        | Voice (rate / volume / pitch) |
|----------|---------|---------|-------------------|-------------------------------|
| Q1       | +       | high    | happy, energetic  | fast, loud, higher pitch      |
| Q2       | −       | high    | upset, agitated   | fast, loud, lower pitch       |
| Q3       | −       | low     | sad, subdued      | slow, soft, lower pitch       |
| Q4       | +       | low     | calm, content     | slow, soft, higher pitch      |

Rate and volume are driven by **arousal**; pitch is driven by **valence** (rendered once a
pitch-capable engine is used — the offline Windows voice applies rate + volume).

## How a turn flows

```
message + quadrant
      │
      ▼
EmotionContract ──► EncodingStrategy ──► prompt + voice params
      │                                        │
      ▼                                        │
   LLM (Ollama) ──► reply + self-assessed emotion
      │                                        │
      ▼                                        │
Coherence gate  (matches target? retry ≤2)     │
      │                                        ▼
      ▼                                   TTS (pyttsx3 / Kokoro)
   accepted reply ─────────────────────────►  speech.wav
      │                                        │
      └──────────────► SQLite provenance log ◄─┘
                       (1 turn row + 1 row per attempt)
```

## Layout (flat scripts)

```
contracts.py       # EmotionContract, quadrants, VA anchors        (SEAM #1)
strategies.py      # EncodingStrategy + SymmetricStrategy; arousal→rate/volume, valence→pitch
prompts/           # 4 quadrant templates (data, not code)
llm.py             # LLMAdapter + Ollama + Mock                     (SEAM #2)
tts.py             # TTSAdapter + Kokoro + pyttsx3 + Mock           (SEAM #2)
gate.py            # coherence gate (pure logic + retry loop)
orchestrator.py    # run_turn: the per-turn pipeline
persistence.py     # SQLite provenance store                       (SEAM #3)
demo.py            # CLI entry point (python demo.py ...)
config.py          # central settings (env vars + defaults)
conftest.py        # puts the project folder on the test path
requirements.txt   # dependencies      pytest.ini  # test discovery
tests/             # one test file per script
```

## Tests
```
pytest        # fast unit + integration (mocks; no Ollama/audio needed)
```

## Inspect the log
```
sqlite3 echo.db "SELECT quadrant, gate_passed, n_attempts, rate, reply FROM turns;"
```

## Scope
**In:** one command, one turn end-to-end, four-quadrant sweep, coherence gate, provenance log.
**Out (later phases):** UI, channel-specialised strategy, real text/speech classifiers,
commercial adapters (OpenAI LLM + Azure TTS), the controlled corpus, the listener study.
