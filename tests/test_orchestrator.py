from pathlib import Path

from llm import MockLLMAdapter
from tts import MockTTSAdapter
from contracts import EmotionContract, Quadrant
from orchestrator import run_turn
from persistence import ProvenanceStore
from strategies import SymmetricStrategy


def _run(tmp_path, quadrant):
    store = ProvenanceStore(str(tmp_path / "echo.db"))
    rec = run_turn(
        EmotionContract.from_quadrant(quadrant),
        "the meeting was moved",
        strategy=SymmetricStrategy(),
        llm=MockLLMAdapter(),          # echoes the prompt's quadrant -> gate passes
        tts=MockTTSAdapter(),
        store=store,
        audio_dir=str(tmp_path / "audio"),
        max_retries=2,
    )
    return store, rec


def test_one_call_makes_one_turn_one_attempt_one_wav(tmp_path):
    store, rec = _run(tmp_path, Quadrant.Q1)
    assert Path(rec.audio_path).exists()
    read = store.read_turn(rec.contract.turn_uuid)
    assert read["turn"]["quadrant"] == "Q1"
    assert read["turn"]["gate_passed"] == 1
    assert len(read["attempts"]) == 1
    assert read["attempts"][0]["accepted"] == 1
    store.close()


def test_full_row_reconstructs(tmp_path):
    store, rec = _run(tmp_path, Quadrant.Q3)
    row = store.read_turn(rec.contract.turn_uuid)["turn"]
    for field in ("message", "model", "strategy", "voice_id", "rate", "engine", "audio_path"):
        assert row[field] not in (None, "")
    assert row["prompt_version"] == "prompts-v1"
    store.close()


def test_retries_exhausted_still_logs_one_turn(tmp_path):
    # Force a permanent mismatch: target Q1 but model always says Q3.
    store = ProvenanceStore(str(tmp_path / "echo.db"))
    scripted = '{"reply": "meh", "self_quadrant": "Q3"}'
    rec = run_turn(
        EmotionContract.from_quadrant(Quadrant.Q1),
        "hello",
        strategy=SymmetricStrategy(),
        llm=MockLLMAdapter(scripted=scripted),
        tts=MockTTSAdapter(),
        store=store,
        audio_dir=str(tmp_path / "audio"),
        max_retries=2,
    )
    read = store.read_turn(rec.contract.turn_uuid)
    assert len(read["attempts"]) == 3       # never exceeds first + 2 retries
    assert read["turn"]["gate_passed"] == 0
    assert sum(a["accepted"] for a in read["attempts"]) == 1
    store.close()


def test_arousal_changes_clip_length(tmp_path):
    _, calm = _run(tmp_path, Quadrant.Q4)   # low arousal -> slower -> longer
    _, excited = _run(tmp_path, Quadrant.Q1)  # high arousal -> faster -> shorter
    assert Path(calm.audio_path).stat().st_size > Path(excited.audio_path).stat().st_size
