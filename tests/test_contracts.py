import json

import pytest
from pydantic import ValidationError

from contracts import (
    EmotionContract,
    Quadrant,
    anchor_for,
    quadrant_for,
)


def test_quadrant_va_roundtrip():
    for q in Quadrant:
        v, a = anchor_for(q)
        assert quadrant_for(v, a) == q


def test_quadrant_axes_and_origin_explicit():
    assert quadrant_for(0.0, 0.0) == Quadrant.Q1  # origin -> Q1 by rule
    assert quadrant_for(0.0, 0.5) == Quadrant.Q1
    assert quadrant_for(-0.1, 0.0) == Quadrant.Q2
    assert quadrant_for(-0.1, -0.1) == Quadrant.Q3
    assert quadrant_for(0.5, -0.1) == Quadrant.Q4


def test_from_quadrant_uses_anchor():
    c = EmotionContract.from_quadrant(Quadrant.Q1)
    assert (c.valence, c.arousal) == anchor_for(Quadrant.Q1)
    assert c.turn_uuid  # generated
    assert c.anchor_version == "va-anchors-v1"


def test_json_roundtrip_lossless():
    c = EmotionContract.from_quadrant(Quadrant.Q3, intensity=0.4, intent="console")
    restored = EmotionContract.model_validate(json.loads(c.model_dump_json()))
    assert restored.quadrant == c.quadrant
    assert restored.valence == c.valence
    assert restored.intensity == c.intensity
    assert restored.intent == c.intent
    assert restored.turn_uuid == c.turn_uuid


@pytest.mark.parametrize(
    "field,value",
    [
        ("valence", 1.5),
        ("valence", -2.0),
        ("arousal", 9.0),
        ("intensity", 1.5),
        ("intensity", -0.1),
    ],
)
def test_invalid_fields_raise(field, value):
    kwargs = dict(quadrant=Quadrant.Q1, valence=0.6, arousal=0.6, intensity=0.7)
    kwargs[field] = value
    with pytest.raises(ValidationError):
        EmotionContract(**kwargs)
