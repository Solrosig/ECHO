"""Encoding strategies: turn an EmotionContract into a text prompt and voice params.

A strategy is a swappable control policy. The MVP ships SymmetricStrategy (same emotion
to both channels). ChannelSpecialisedStrategy is deferred to Phase F4 and would sit behind
the same interface, so nothing downstream changes.

Every engine-agnostic voice dial blends both axes in two tiers (primary axis dominant,
secondary axis a small shift):
  - rate   (speaking speed) <- arousal (primary) + valence (secondary, +)
  - volume (loudness)       <- arousal (primary) - valence (secondary; +valence = softer)
  - pitch  (voice height)   <- valence (primary) + arousal (secondary)

The secondary term makes all four quadrants distinct on every dial, so Q1 'happy' and
Q2 'upset' (same arousal) differ audibly, while the Q1<->Q2 gap stays smaller than the
Q1<->Q3 (cross-arousal) gap.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path

from contracts import EmotionContract, Quadrant

# v2 (2026-08-23, story G6.1): the four templates no longer pre-fill `self_quadrant`.
# v1 put the answer key in the output format ({"reply": ..., "self_quadrant": "Q2"}), so
# the "self-assessment" was a copy, not a judgement. An independent EmotionJudge
# (judge.py) now judges emotion.
PROMPT_VERSION = "prompts-v2"

# Emotion -> dial mapping. Linear valence(V)/arousal(A) model in the tradition of the
# MARY TTS / Schroeder emotion rules, as extracted and re-validated by
# Burkhardt, Reichel, Eyben & Schuller (2023) "Going Retro..." (ESSV) and Schroeder (2004).
# Each dial is a weighted sum of A and V, following the reported acoustic correlates:
#   * high arousal     -> faster rate, higher intensity, higher F0
#                         (Schroeder: rate=0.5A, volume=0.33A, pitch=0.3A)
#   * positive valence -> faster rate but lower intensity; pitch carries valence best
#                         (Syntact variant: pitch<-valence gave the best valence UAR)
#
# Two-tier weights (primary dominates, secondary refines):
#   dial   | primary (Tier 1)          | secondary (Tier 2)        | valence sign
#   -------|---------------------------|---------------------------|-------------
#   rate   | arousal (RATE_AROUSAL_W)  | valence (RATE_VALENCE_W)  |  +  (faster)
#   volume | arousal (VOL_AROUSAL_W)   | valence (VOL_VALENCE_W)   |  -  (softer)
#   pitch  | valence (VALENCE_PITCH_W) | arousal (AROUSAL_PITCH_W) |  +  (higher)
#
# Consequence (matches emotion acoustics): Q2 'upset' = loudest, and lower-pitched than
# Q1 (neg V, high A); Q1 'happy' = fastest + highest pitch; Q3 'sad' = slowest + lowest
# pitch; Q4 'calm' = softest. Known limitation: a linear V/A model gives 'upset' a low pitch, whereas hot
# anger also has high F0. Separating anger from fear needs the dominance dimension or
# voice quality (Burkhardt et al. 2023, deferred to a later phase).

RATE_MIN, RATE_MAX = 0.7, 1.3     # clamp bounds for the rate factor
RATE_AROUSAL_W = 0.20             # A -> rate (primary): fast when excited     (Schroeder 0.5)
RATE_VALENCE_W = 0.08             # V -> rate (secondary, added): positive a touch faster (Schroeder 0.2)

VOL_MIN, VOL_MAX = 0.6, 1.0       # clamp bounds for loudness
VOL_AROUSAL_W = 0.20              # A -> volume (primary): loud when excited   (Schroeder 0.33)
VOL_VALENCE_W = 0.05              # V -> volume (secondary, subtracted): positive valence = softer

PITCH_MIN, PITCH_MAX = 0.8, 1.2   # clamp bounds for pitch
VALENCE_PITCH_W = 0.22            # V -> pitch (primary channel; Syntact: pitch carries valence)
AROUSAL_PITCH_W = 0.15            # A -> pitch (secondary): higher when excited (Schroeder 0.3)


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def arousal_to_rate(arousal: float) -> float:
    """Arousal-only rate component (primary tier). Monotonic in arousal, clamped."""
    return _clamp(1.0 + RATE_AROUSAL_W * arousal, RATE_MIN, RATE_MAX)


def emotion_to_rate(valence: float, arousal: float) -> float:
    """Rate from arousal (primary) plus a small valence shift (secondary), clamped."""
    return _clamp(1.0 + RATE_AROUSAL_W * arousal + RATE_VALENCE_W * valence, RATE_MIN, RATE_MAX)


def arousal_to_volume(arousal: float) -> float:
    """Arousal-only loudness component (primary tier). Monotonic, clamped.

    0.8 + 0.2*arousal is identical to the old VOL_MIN + (a+1)/2 * span.
    """
    return _clamp(0.8 + VOL_AROUSAL_W * arousal, VOL_MIN, VOL_MAX)


def emotion_to_volume(valence: float, arousal: float) -> float:
    """Loudness from arousal (primary) minus a small valence term, clamped.

    Positive valence lowers intensity (per the acoustic correlates), so Q2 'upset' is the
    louder of the high-arousal pair (anger = high intensity).
    """
    return _clamp(0.8 + VOL_AROUSAL_W * arousal - VOL_VALENCE_W * valence, VOL_MIN, VOL_MAX)


def emotion_to_pitch(valence: float, arousal: float) -> float:
    """Pitch from valence (primary) plus arousal (secondary); monotonic in each, clamped."""
    return _clamp(
        1.0 + AROUSAL_PITCH_W * arousal + VALENCE_PITCH_W * valence,
        PITCH_MIN,
        PITCH_MAX,
    )


@dataclass(frozen=True)
class VoiceParams:
    """Engine-agnostic voice parameters produced by a strategy.

    Carries the prosodic projection of the emotion (rate/volume/pitch, for engines with
    those dials) and the emotion itself (valence/arousal/intensity/quadrant, for engines
    with native emotion conditioning, e.g. an expressiveness scalar or a per-quadrant
    reference style).

    Why both (Phase-N result): a neutral neural engine ignores externally applied prosody,
    so emotion must reach it through the engine's own conditioning interface. The emotion
    fields have neutral defaults, so existing adapters and tests are unaffected.
    """

    voice_id: str
    rate: float           # speed factor; 1.0 = natural pace     (arousal + valence)
    volume: float = 1.0   # loudness 0..1                        (arousal - valence)
    pitch: float = 1.0    # relative voice height; 1.0 = normal  (valence + arousal)
    valence: float = 0.0    # -1..1  pleasantness  (native-conditioning engines)
    arousal: float = 0.0    # -1..1  activation    (native-conditioning engines)
    intensity: float = 0.0  # 0..1   emotion strength
    quadrant: str = ""      # "Q1".."Q4": selects a per-quadrant reference style


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
    """Sends the full target emotion to both the text and the voice channel."""

    name = "symmetric"

    def __init__(self, voice_id: str = "af_heart") -> None:
        self._voice_id = voice_id

    def build_prompt(self, contract: EmotionContract, message: str) -> str:
        template = _load_template(contract.quadrant)
        return template.format(message=message)

    def build_voice_params(self, contract: EmotionContract) -> VoiceParams:
        return VoiceParams(
            voice_id=self._voice_id,
            rate=emotion_to_rate(contract.valence, contract.arousal),
            volume=emotion_to_volume(contract.valence, contract.arousal),
            pitch=emotion_to_pitch(contract.valence, contract.arousal),
            # the emotion itself, for engines that condition natively rather than on prosody
            valence=contract.valence,
            arousal=contract.arousal,
            intensity=contract.intensity,
            quadrant=contract.quadrant.value,
        )
