"""SAPI dial calibration + expressiveness. The intended dials must map onto SAPI's
scale so the four quadrants are (a) clearly DISTINCT from each other and (b) still
listenable. Guards both regressions: 'too fast / unlistenable' and 'all sound the same'."""

from contracts import EmotionContract, Quadrant
from strategies import SymmetricStrategy
from tts import _sapi_pitch, _sapi_rate, _sapi_volume


def test_rate_is_expressive_but_capped():
    assert _sapi_rate(1.0) == 0
    assert _sapi_rate(1.18) == 3          # high-arousal quadrant: clearly fast (~1.4x)
    assert _sapi_rate(0.82) == -3         # low-arousal quadrant: clearly slow (~0.7x)
    assert _sapi_rate(1.3) <= 5           # extreme is capped listenable, NOT SAPI's +10 (~3x)
    assert _sapi_rate(1.3) > _sapi_rate(1.0) > _sapi_rate(0.7)


def test_pitch_carries_valence_without_chipmunking():
    assert _sapi_pitch(1.0) == 0
    assert _sapi_pitch(1.2) == 4          # top pitch: audible, never chipmunk
    assert _sapi_pitch(0.8) == -4
    assert _sapi_pitch(1.2) != _sapi_pitch(0.958)   # happy vs upset stay distinct


def test_volume_has_wide_dynamic_range():
    assert _sapi_volume(0.92) - _sapi_volume(0.68) >= 20   # loud clearly louder than soft
    assert _sapi_volume(1.0) <= 95
    assert _sapi_volume(0.6) >= 40                         # softest is still audible


def test_four_quadrants_render_distinct():
    """The core requirement: all four emotions must be audibly different when rendered."""
    strat = SymmetricStrategy()
    triples = {}
    for q in Quadrant:
        vp = strat.build_voice_params(EmotionContract.from_quadrant(q))
        triples[q] = (_sapi_rate(vp.rate), _sapi_volume(vp.volume), _sapi_pitch(vp.pitch))

    assert len(set(triples.values())) == 4                # four distinct (speed, volume, pitch)
    # valence lives in pitch: happy > upset, calm > sad (each pair shares arousal)
    assert triples[Quadrant.Q1][2] > triples[Quadrant.Q2][2]
    assert triples[Quadrant.Q4][2] > triples[Quadrant.Q3][2]
    # arousal lives in rate + volume: happy is both faster and louder than sad
    assert triples[Quadrant.Q1][0] > triples[Quadrant.Q3][0]
    assert triples[Quadrant.Q1][1] > triples[Quadrant.Q3][1]
