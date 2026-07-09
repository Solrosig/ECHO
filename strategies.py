"""Encoding strategies — turn an EmotionContract into a text prompt and voice params.

The strategy is a swappable control policy. The MVP ships SymmetricStrategy (same
emotion to both channels). Phase 4 will add ChannelSpecialisedStrategy behind this
same interface, so nothing downstream changes.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path

from contracts import EmotionContract, Quadrant

PROMPT_VERSION = "prompts-v1"

# Arousal -> speech rate. Stored as data (endpoints), applied by a monotonic formula.
# arousal -1 -> RATE_MIN (slow), +1 -> RATE_MAX (fast), 0 -> 1.0.
RATE_MIN = 0.7
RATE_MAX = 1.3


def arousal_to_rate(arousal: float) -> float:
    """Monotonic map arousal in [-1, 1] to a clamped speech-rate factor."""
    rate = 1.0 + arousal * (RATE_MAX - 1.0)
    return max(RATE_MIN, min(RATE_MAX, rate))


@dataclass(frozen=True)
class VoiceParams:
    """Engine-agnostic voice parameters produced by a strategy."""

    voice_id: str
    rate: float  # speed factor; 1.0 = natural pace


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
        # Symmetric: arousal drives pace directly from the same contract.
        return VoiceParams(voice_id=self._voice_id, rate=arousal_to_rate(contract.arousal))
