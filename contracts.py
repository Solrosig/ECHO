"""EmotionContract: the single data structure carried through the whole pipeline.

Protected seam #1: change only with review.

Emotion is modelled on Russell's valence-arousal circumplex, discretised into four quadrants:

    arousal +
            |
      Q2    |    Q1
  (v<0,a>=0)| (v>=0,a>=0)
  ----------+----------  valence +
      Q3    |    Q4
   (v<0,a<0)| (v>=0,a<0)
            |
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field

# Quadrant anchors are versioned by ANCHOR_VERSION. Do not edit values silently.
ANCHOR_VERSION = "va-anchors-v1"


class Quadrant(str, Enum):
    Q1 = "Q1"  # positive valence, high arousal: excited / happy
    Q2 = "Q2"  # negative valence, high arousal: angry / afraid
    Q3 = "Q3"  # negative valence, low arousal: sad / bored
    Q4 = "Q4"  # positive valence, low arousal: calm / content


# (valence, arousal) anchor for each quadrant
_ANCHORS: dict[Quadrant, tuple[float, float]] = {
    Quadrant.Q1: (0.6, 0.6),
    Quadrant.Q2: (-0.6, 0.6),
    Quadrant.Q3: (-0.6, -0.6),
    Quadrant.Q4: (0.6, -0.6),
}

# Human-readable label per quadrant (EmotionContract.label).
QUADRANT_LABEL: dict[Quadrant, str] = {
    Quadrant.Q1: "happy and energetic",
    Quadrant.Q2: "upset and agitated",
    Quadrant.Q3: "sad and subdued",
    Quadrant.Q4: "calm and content",
}


def anchor_for(quadrant: Quadrant) -> tuple[float, float]:
    """Return the (valence, arousal) anchor for a quadrant."""
    return _ANCHORS[quadrant]


def quadrant_for(valence: float, arousal: float) -> Quadrant:
    """Map a (valence, arousal) point to a quadrant.

    On the axes, valence>=0 counts as positive and arousal>=0 as high, so (0, 0) -> Q1.
    """
    if valence >= 0 and arousal >= 0:
        return Quadrant.Q1
    if valence < 0 and arousal >= 0:
        return Quadrant.Q2
    if valence < 0 and arousal < 0:
        return Quadrant.Q3
    return Quadrant.Q4  # valence >= 0 and arousal < 0


class EmotionContract(BaseModel):
    """The chosen emotion, carried unchanged through every stage of a turn."""

    quadrant: Quadrant
    valence: float = Field(..., ge=-1.0, le=1.0)
    arousal: float = Field(..., ge=-1.0, le=1.0)
    intensity: float = Field(..., ge=0.0, le=1.0)
    intent: str = "inform"
    turn_uuid: str = Field(default_factory=lambda: str(uuid.uuid4()))
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    anchor_version: str = ANCHOR_VERSION

    @classmethod
    def from_quadrant(
        cls,
        quadrant: Quadrant,
        *,
        intensity: float = 0.7,
        intent: str = "inform",
    ) -> "EmotionContract":
        """Build a contract from a quadrant using its versioned anchor."""
        v, a = anchor_for(quadrant)
        return cls(
            quadrant=quadrant,
            valence=v,
            arousal=a,
            intensity=intensity,
            intent=intent,
        )

    @property
    def label(self) -> str:
        return QUADRANT_LABEL[self.quadrant]
