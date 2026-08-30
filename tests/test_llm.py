from llm import MockLLMAdapter, parse_llm_json
from contracts import Quadrant


def test_parse_clean_json():
    reply, q = parse_llm_json('{"reply": "hi there", "self_quadrant": "Q1"}')
    assert reply == "hi there"
    assert q == Quadrant.Q1


def test_parse_fenced_json():
    text = '```json\n{"reply": "ok", "self_quadrant": "Q3"}\n```'
    reply, q = parse_llm_json(text)
    assert reply == "ok"
    assert q == Quadrant.Q3


def test_parse_with_surrounding_prose():
    text = 'Sure!\n{"reply": "calm down", "self_quadrant": "Q4"} hope that helps'
    reply, q = parse_llm_json(text)
    assert reply == "calm down"
    assert q == Quadrant.Q4


def test_parse_malformed_degrades_gracefully():
    text = "totally not json at all"
    reply, q = parse_llm_json(text)
    assert reply == "totally not json at all"
    assert q is None


def test_parse_bad_quadrant_label():
    reply, q = parse_llm_json('{"reply": "x", "self_quadrant": "Q9"}')
    assert reply == "x"
    assert q is None


def test_mock_adapter_complies_with_the_emotion_the_prompt_asks_for():
    # Since G6.1 the prompt no longer names the quadrant, so the mock reads the
    # emotion description - the same cue a real model has.
    adapter = MockLLMAdapter()
    result = adapter.generate("Your reply must sound UPSET and AGITATED (negative...)")
    assert result.self_quadrant == Quadrant.Q2
    assert result.model_id == "mock"


def test_mock_adapter_defaults_when_no_cue_present():
    assert MockLLMAdapter().generate("no emotion cue here").self_quadrant == Quadrant.Q1
