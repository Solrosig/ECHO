import pytest

from contracts import EmotionContract, Quadrant
from strategies import (
    RATE_MAX,
    RATE_MIN,
    VOL_MAX,
    VOL_MIN,
    SymmetricStrategy,
    VoiceParams,
    arousal_to_rate,
    arousal_to_volume,
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


def test_symmetric_prompt_contains_message_and_quadrant_json():
    strat = SymmetricStrategy()
    c = EmotionContract.from_quadrant(Quadrant.Q2)
    prompt = strat.build_prompt(c, "the bus was late")
    assert "the bus was late" in prompt
    assert '"self_quadrant": "Q2"' in prompt


def test_symmetric_voice_params_reflect_arousal():
    strat = SymmetricStrategy()
    calm = strat.build_voice_params(EmotionContract.from_quadrant(Quadrant.Q4))
    excited = strat.build_voice_params(EmotionContract.from_quadrant(Quadrant.Q1))
    assert isinstance(calm, VoiceParams)
    assert excited.rate > calm.rate  # higher arousal -> faster
    assert excited.volume > calm.volume  # higher arousal -> louder


def test_all_four_templates_render():
    strat = SymmetricStrategy()
    for q in Quadrant:
        prompt = strat.build_prompt(EmotionContract.from_quadrant(q), "hello")
        assert f'"self_quadrant": "{q.value}"' in prompt
