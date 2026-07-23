"""SAPI dial calibration: the intended gentle dials must map onto SAPI's SMALL
range, not its extremes. Guards against the 'too fast / too loud' regression where
a 1.3x rate rendered as ~2-3x actual speed."""

from tts import _sapi_pitch, _sapi_rate, _sapi_volume


def test_rate_is_a_mild_speedup_not_extreme():
    assert _sapi_rate(1.0) == 0                 # neutral is neutral
    assert 0 < _sapi_rate(1.3) <= 3             # top rate = mild, NOT SAPI's +10 (~3x)
    assert -3 <= _sapi_rate(0.7) < 0            # bottom rate = mild slow-down
    assert _sapi_rate(1.3) > _sapi_rate(1.0) > _sapi_rate(0.7)   # monotonic


def test_pitch_shift_is_gentle_and_distinct():
    assert _sapi_pitch(1.0) == 0
    assert 0 < _sapi_pitch(1.15) <= 4           # audible but never chipmunk
    assert -4 <= _sapi_pitch(0.85) < 0
    assert _sapi_pitch(1.15) != _sapi_pitch(1.03)   # quadrants stay distinguishable


def test_volume_present_but_capped():
    assert _sapi_volume(1.0) <= 90              # ceiling: present, not blasting
    assert _sapi_volume(1.0) > _sapi_volume(0.6)
