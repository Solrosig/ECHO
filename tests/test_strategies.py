import pytest

from contracts import EmotionContract, Quadrant
from strategies import (
    PITCH_MAX, PITCH_MIN, RATE_MAX, RATE_MIN, VOL_MAX, VOL_MIN,
    SymmetricStrategy, VoiceParams, arousal_to_rate, arousal_to_volume, valence_to_pitch,
)


def test_arousal_rate_monotonic_and_clamped():
    rates = [arousal_to_rate(a / 10) for a in range(-10, 11)]
    assert rates == sorted(rates)
    assert min(rates) >= RATE_MIN and max(rates) <= RATE_MAX
    assert arousal_to_rate(0.0) == pytest.approx(1.0)


def test_arousal_volume_monotonic_and_clamped():
    vols = [arousal_to_volume(a / 10) for a in range(-10, 11)]
    assert vols == sorted(vols)
    assert min(vols) >= VOL_MIN and max(vols) <= VOL_MAX


def test_valence_pitch_monotonic_and_clamped():
    pitches = [valence_to_pitch(v / 10) for v in range(-10, 11)]
    assert pitches == sorted(pitches)
    assert min(pitches) >= PITCH_MIN and max(pitches) <= PITCH_MAX
    assert valence_to_pitch(0.0) == pytest.approx(1.0)


def test_symmetric_prompt_contains_message_and_quadrant_json():
    strat = SymmetricStrategy()
    c = EmotionContract.from_quadrant(Quadrant.Q2)
    prompt = strat.build_prompt(c, "the bus was late")
    assert "the bus was late" in prompt
    assert '"self_quadrant": "Q2"' in prompt


def test_voice_params_reflect_arousal_and_valence():
    strat = SymmetricStrategy()
    q1 = strat.build_voice_params(EmotionContract.from_quadrant(Quadrant.Q1))  # v+ a+
    q2 = strat.build_voice_params(EmotionContract.from_quadrant(Quadrant.Q2))  # v- a+
    q3 = strat.build_voice_params(EmotionContract.from_quadrant(Quadrant.Q3))  # v- a-
    assert isinstance(q1, VoiceParams)
    assert q1.rate > q3.rate            # higher arousal -> faster
    assert q1.volume > q3.volume        # higher arousal -> louder
    assert q1.pitch > q2.pitch          # higher valence -> higher pitch


def test_all_four_templates_render():
    strat = SymmetricStrategy()
    for q in Quadrant:
        prompt = strat.build_prompt(EmotionContract.from_quadrant(q), "hello")
        assert f'"self_quadrant": "{q.value}"' in prompt
