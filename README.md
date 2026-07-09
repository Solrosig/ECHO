# ECHO
Emotionally CoHerent cOnversational system: Emotionally Coherent Conversational System for Text and Speech Generation

Emotion-conditioned text **and** speech, in one command. You give ECHO a message and a
target emotion (a quadrant on the valence–arousal plane); it generates a reply in that
emotion, checks the reply actually *sounds* like that emotion, speaks it with a pace that
reflects arousal, and logs the whole turn to a database. Open-source, local, no cloud, no cost.

```
echo-run "The meeting was moved to a different room" --all-quadrants
```
→ four replies (happy / upset / sad / calm), four spoken clips, four fully-logged turns.

## What it demonstrates

The project's main risk is the connection link between the independent **text** and **speech** channels.
This MVP proves that the connection link works end to end: one `EmotionContract` flows through generation,
a coherence gate, speech synthesis, and provenance logging — every swappable part
(`EncodingStrategy`, `LLMAdapter`, `TTSAdapter`) sits behind a stable interface so later
phases add a class instead of rewriting the pipeline.

## Quickstart (Windows)

### 1. Install Ollama (the language model)
1. Download and install from https://ollama.com/download
2. Pull the model:
   ```
   ollama pull llama3.2:3b
   ```
3. Ollama serves automatically at `http://localhost:11434`.

### 2. Set up Python
```
cd "path\to\echo"
python -m venv .venv
.venv\Scripts\activate
pip install -e ".[dev]"
```

### 3. Run it
```
echo-run "The bus was late this morning" --all-quadrants
```
Speech uses **pyttsx3** (built-in Windows voices) out of the box — no extra setup.

### 4. (Optional) Better voice with Kokoro
For higher-quality neural speech:
```
pip install -e ".[kokoro]"
```
Download `kokoro-v1.0.onnx` and `voices-v1.0.bin` from the
[kokoro-onnx releases page](https://github.com/thewh1teagle/kokoro-onnx/releases) into the
project folder, then:
```
set ECHO_TTS_ENGINE=kokoro
echo-run "The bus was late this morning" --all-quadrants
```

### No external tools? Run the offline demo
```
echo-run "The bus was late this morning" --all-quadrants --mock
```
Uses stub LLM/TTS so the full pipeline (gate, logging, arousal→pace) runs with zero deps.

## The four emotions (Russell circumplex quadrants)

| Quadrant | Valence | Arousal | Feels like        | Speech pace |
|----------|---------|---------|-------------------|-------------|
| Q1       | +       | high    | happy, energetic  | faster      |
| Q2       | −       | high    | upset, agitated   | faster      |
| Q3       | −       | low     | sad, subdued      | slower      |
| Q4       | +       | low     | calm, content     | slower      |

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
      ▼                                   TTS (Kokoro/pyttsx3)
   accepted reply ─────────────────────────►  speech.wav
      │                                        │
      └──────────────► SQLite provenance log ◄─┘
                       (1 turn row + 1 row per attempt)
```

## Inspect the log
```
sqlite3 echo.db "SELECT quadrant, gate_passed, n_attempts, rate, reply FROM turns;"
```

## Commands
```
echo-run "<message>" --quadrant Q1        # one emotion
echo-run "<message>" --all-quadrants      # sweep Q1..Q4
echo-run "<message>" --all-quadrants --mock      # no external tools
echo-run "<message>" --quadrant Q3 --no-audio    # synthesise but don't play
```

## Tests
```
pytest -m "not slow"     # fast unit + integration (mocks; no Ollama/TTS needed)
```

## Layout
```
echo/
├── contracts.py      # EmotionContract, quadrants, VA anchors   (SEAM #1)
├── strategies.py     # EncodingStrategy + SymmetricStrategy, arousal→rate
├── prompts/          # 4 quadrant templates (data, not code)
├── adapters/
│   ├── llm.py        # LLMAdapter + Ollama + Mock               (SEAM #2)
│   └── tts.py        # TTSAdapter + Kokoro + pyttsx3 + Mock      (SEAM #2)
├── gate.py           # coherence gate (pure logic + retry loop)
├── orchestrator.py   # run_turn: the per-turn pipeline
├── persistence.py    # SQLite provenance store                  (SEAM #3)
└── demo.py           # CLI entry point
```

## Scope
**In:** one command, one turn end-to-end, four-quadrant sweep, coherence gate, provenance log.
**Out (later phases):** UI, channel-specialised strategy, real text/speech classifiers,
commercial adapters, the controlled corpus, the listener study.
