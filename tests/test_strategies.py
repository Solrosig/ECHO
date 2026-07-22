import pytest

from contracts import EmotionContract, Quadrant
from strategies import (
    PITCH_MAX,
    PITCH_MIN,
    RATE_MAX,
    RATE_MIN,
    VOL_MAX,
    VOL_MIN,
    SymmetricStrategy,
    VoiceParams,
    arousal_to_rate,
    arousal_to_volume,
    emotion_to_pitch,
)


def test_arousal_rate_monotonic_and_clamped():
    rates = [arousal_to_rate(a / 10) for a in range(-10, 11)]
    assert rates == sorted(rates)  # non-decreasing
    assert min(rates) >= RATE_MIN
    assert max(rates) <= RATE_MAX
    assert arousal_to_rate(0.0) == pytest.approx(1.0)


def test_arousal_volume_monotonic_and_clamped():
    vols = [arousal_to_volume(a / 10) for a in range(-10, 11)]
    assert vols == sorted(vols)  # louder as arousal rises
    assert min(vols) >= VOL_MIN
    assert max(vols) <= VOL_MAX


def test_pitch_rises_with_valence_and_arousal_and_clamped():
    # monotonic in valence (arousal fixed)
    pv = [emotion_to_pitch(v / 10, 0.0) for v in range(-10, 11)]
    assert pv == sorted(pv)
    # monotonic in arousal (valence fixed)
    pa = [emotion_to_pitch(0.0, a / 10) for a in range(-10, 11)]
    assert pa == sorted(pa)
    # clamped
    allp = [emotion_to_pitch(v / 10, a / 10) for v in range(-10, 11) for a in range(-10, 11)]
    assert min(allp) >= PITCH_MIN
    assert max(allp) <= PITCH_MAX


def test_four_quadrants_have_distinct_pitch():
    strat = SymmetricStrategy()
    pitches = {q: strat.build_voice_params(EmotionContract.from_quadrant(q)).pitch for q in Quadrant}
    assert len({round(p, 4) for p in pitches.values()}) == 4  # all four differ


def test_symmetric_prompt_contains_message_and_quadrant_json():
    strat = SymmetricStrategy()
    c = EmotionContract.from_quadrant(Quadrant.Q2)
    prompt = strat.build_prompt(c, "the bus was late")
    assert "the bus was late" in prompt
    assert '"self_quadrant": "Q2"' in prompt


def test_symmetric_voice_params_reflect_both_axes():
    strat = SymmetricStrategy()
    q1 = strat.build_voice_params(EmotionContract.from_quadrant(Quadrant.Q1))  # v+ a+
    q2 = strat.build_voice_params(EmotionContract.from_quadrant(Quadrant.Q2))  # v- a+
    q3 = strat.build_voice_params(EmotionContract.from_quadrant(Quadrant.Q3))  # v- a-
    q4 = strat.build_voice_params(EmotionContract.from_quadrant(Quadrant.Q4))  # v+ a-
    assert isinstance(q1, VoiceParams)
    assert q1.rate > q3.rate  # arousal -> faster
    assert q1.volume > q3.volume  # arousal -> louder
    assert q1.pitch > q2.pitch  # valence -> higher pitch (same arousal)
    assert q1.pitch > q4.pitch  # arousal -> higher pitch (same valence)


def test_all_four_templates_render():
    strat = SymmetricStrategy()
    for q in Quadrant:
        prompt = strat.build_prompt(EmotionContract.from_quadrant(q), "hello")
        assert f'"self_quadrant": "{q.value}"' in prompt
