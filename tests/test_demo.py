"""Demo CLI tests (Story E9.1) — the runtime engine switch. Uses the mock LLM + mock
TTS engine and a temp DB/audio dir so no external tools (Ollama/SAPI) are needed."""

import demo
from config import Config


def _tmp_cfg(tmp_path):
    (tmp_path / "audio").mkdir(exist_ok=True)
    return Config(db_path=str(tmp_path / "e.db"), audio_dir=str(tmp_path / "audio"))


def test_engine_flag_selects_tts_end_to_end(tmp_path, monkeypatch):
    monkeypatch.setattr(demo, "load_config", lambda: _tmp_cfg(tmp_path))
    rc = demo.main(["hello there", "--quadrant", "Q1", "--mock", "--engine", "mock", "--no-audio"])
    assert rc == 0


def test_mock_defaults_to_mock_engine(tmp_path, monkeypatch):
    monkeypatch.setattr(demo, "load_config", lambda: _tmp_cfg(tmp_path))
    rc = demo.main(["the bus was late", "--quadrant", "Q2", "--mock", "--no-audio"])
    assert rc == 0
