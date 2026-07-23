# ECHO — MVP

Emotion-conditioned text **and** speech, in one command. You give ECHO a message and a
target emotion (a quadrant on the valence–arousal plane); it generates a reply in that
emotion, checks the reply actually *sounds* like that emotion, speaks it with a pace,
loudness, and pitch that reflect the emotion, and logs the whole turn to a database. Open-source,
local, no cloud, no cost.

```
python demo.py "The meeting was moved to a different room" --all-quadrants
```
→ four replies (happy / upset / sad / calm), four spoken clips, four fully-logged turns.

## What it demonstrates

The project's main risk is the connection between the independent **text** and **speech** channels.
This MVP proves that seam works end to end: one `EmotionContract` flows through generation,
a coherence gate, speech synthesis, and provenance logging — every swappable part
(`EncodingStrategy`, `LLMAdapter`, `TTSAdapter`) sits behind a stable interface so later
phases add a class instead of rewriting the pipeline.

## MVP Scope
**In:** one command, one turn end-to-end, four-quadrant sweep, coherence gate, provenance log.
**Out:** UI, channel-specialised strategy, real text/speech classifiers,
commercial adapters (OpenAI LLM + Azure TTS), the controlled corpus, the listener study.


## The four emotions (Russell circumplex quadrants)

| Quadrant | Valence | Arousal | Feels like        | Voice (rate / volume / pitch) |
|----------|---------|---------|-------------------|-------------------------------|
| Q1       | +       | high    | happy, energetic  | fast, loud, higher pitch      |
| Q2       | −       | high    | upset, agitated   | fast, loud, lower pitch       |
| Q3       | −       | low     | sad, subdued      | slow, soft, lower pitch       |
| Q4       | +       | low     | calm, content     | slow, soft, higher pitch      |

Rate and volume are driven by **arousal**; pitch is driven by **arousal + valence** (blended so all
four quadrants differ). The **SAPI** engine (`ECHO_TTS_ENGINE=sapi`) renders pitch; the `pyttsx3`
and `Kokoro` engines render rate + volume. `rate`, `volume`, and `pitch` are logged per turn.

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
      ▼                                   TTS (pyttsx3 / SAPI / Kokoro)
   accepted reply ─────────────────────────►  speech.wav
      │                                        │
      └──────────────► SQLite provenance log ◄─┘
                       (1 turn row + 1 row per attempt)
```

## Layout

```
contracts.py       # EmotionContract, quadrants, VA anchors        (Block #1)
strategies.py      # EncodingStrategy + SymmetricStrategy; arousal→rate/volume, valence→pitch
prompts/           # 4 quadrant templates (data, not code)
llm.py             # LLMAdapter + Ollama + Mock                     (Block #2)
tts.py             # TTSAdapter + Kokoro + pyttsx3 + Mock           (Block #2)
gate.py            # coherence gate (pure logic + retry loop)
orchestrator.py    # run_turn: the per-turn pipeline
persistence.py     # SQLite provenance store                       (Block #3)
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

## MVP Scope
**In:** one command, one turn end-to-end, four-quadrant sweep, coherence gate, provenance log.
**Out:** UI, channel-specialised strategy, real text/speech classifiers,
commercial adapters (OpenAI LLM + Azure TTS), the controlled corpus, the listener study.
## Stage 1
**UI
