"""Encoding strategies — turn an EmotionContract into a text prompt and voice params.

The strategy is a swappable control policy. The MVP ships SymmetricStrategy (same
emotion to both channels). Phase 4 will add ChannelSpecialisedStrategy behind this
same interface, so nothing downstream changes.

Engine-agnostic voice dials, derived from the contract:
  - rate   (speaking speed) <- arousal            (fast when excited, slow when calm)
  - volume (loudness)       <- arousal            (loud when excited, soft when subdued)
  - pitch  (voice height)   <- arousal AND valence (higher when excited/positive)

Pitch blends both axes on purpose: arousal sets the base height and valence shifts
it, so the four quadrants get four distinct pitches (this is what separates Q1
'happy' from Q2 'upset', which share arousal).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path

from contracts import EmotionContract, Quadrant

PROMPT_VERSION = "prompts-v1"

# Arousal -> speech rate (endpoints as data; monotonic). -1 slow .. +1 fast.
RATE_MIN = 0.7
RATE_MAX = 1.3

# Arousal -> loudness. -1 -> VOL_MIN (soft), +1 -> VOL_MAX (loud).
VOL_MIN = 0.6
VOL_MAX = 1.0

# (arousal, valence) -> pitch (voice height), around 1.0.
PITCH_MIN, PITCH_MAX = 0.8, 1.2
AROUSAL_PITCH_W = 0.15   # arousal raises pitch
VALENCE_PITCH_W = 0.10   # positive valence raises pitch further


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def arousal_to_rate(arousal: float) -> float:
    """Monotonic map arousal in [-1, 1] to a clamped speech-rate factor."""
    return _clamp(1.0 + arousal * (RATE_MAX - 1.0), RATE_MIN, RATE_MAX)


def arousal_to_volume(arousal: float) -> float:
    """Monotonic map arousal in [-1, 1] to a clamped loudness in [VOL_MIN, VOL_MAX]."""
    return _clamp(VOL_MIN + (arousal + 1.0) / 2.0 * (VOL_MAX - VOL_MIN), VOL_MIN, VOL_MAX)


def emotion_to_pitch(valence: float, arousal: float) -> float:
    """Map emotion to a clamped pitch factor around 1.0.

    Arousal sets the base height; valence shifts it. Monotonic in each axis, so
    all four quadrants receive distinct pitches.
    """
    return _clamp(
        1.0 + AROUSAL_PITCH_W * arousal + VALENCE_PITCH_W * valence,
        PITCH_MIN,
        PITCH_MAX,
    )


@dataclass(frozen=True)
class VoiceParams:
    """Engine-agnostic voice parameters produced by a strategy."""

    voice_id: str
    rate: float           # speed factor; 1.0 = natural pace     (from arousal)
    volume: float = 1.0   # loudness 0..1                        (from arousal)
    pitch: float = 1.0    # relative voice height; 1.0 = normal  (from arousal+valence)


_PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"


def _load_template(quadrant: Quadrant) -> str:
    fname = f"{quadrant.value.lower()}.txt"
    return (_PROMPTS_DIR / fname).read_text(encoding="utf-8")


class EncodingStrategy(ABC):
    """Maps a contract to (prompt, voice params)."""

    name: str = "base"

    @abstractmethod
    def build_prompt(self, contract: EmotionContract, message: str) -> str: ...

    @abstractmethod
    def build_voice_params(self, contract: EmotionContract) -> VoiceParams: ...


class SymmetricStrategy(EncodingStrategy):
    """Sends the full target emotion to BOTH the text and the voice channel."""

    name = "symmetric"

    def __init__(self, voice_id: str = "af_heart") -> None:
        self._voice_id = voice_id

    def build_prompt(self, contract: EmotionContract, message: str) -> str:
        template = _load_template(contract.quadrant)
        return template.format(message=message)

    def build_voice_params(self, contract: EmotionContract) -> VoiceParams:
        # Symmetric: the same contract drives pace, loudness, and pitch.
        return VoiceParams(
            voice_id=self._voice_id,
            rate=arousal_to_rate(contract.arousal),
            volume=arousal_to_volume(contract.arousal),
            pitch=emotion_to_pitch(contract.valence, contract.arousal),
        )
