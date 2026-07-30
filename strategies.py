"""Encoding strategies — turn an EmotionContract into a text prompt and voice params.

The strategy is a swappable control policy. The MVP ships SymmetricStrategy (same
emotion to both channels). Phase 4 will add ChannelSpecialisedStrategy behind this
same interface, so nothing downstream changes.

Engine-agnostic voice dials, derived from the contract. EVERY dial blends BOTH axes
in a two-tier scheme (primary axis dominant, secondary axis a small shift):
  - rate   (speaking speed) <- arousal (primary) + valence (secondary, +)
  - volume (loudness)       <- arousal (primary) - valence (secondary; +valence = softer)
  - pitch  (voice height)   <- valence (primary) + arousal (secondary)

Because each dial carries a little valence, all four quadrants are distinct on every
dial -- but arousal still dominates pace/loudness and valence dominates pitch. This is
what makes Q1 'happy' and Q2 'upset' (which share arousal) audibly different everywhere,
while keeping the Q1<->Q2 gap smaller than the Q1<->Q3 (cross-arousal) gap.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path

from contracts import EmotionContract, Quadrant

PROMPT_VERSION = "prompts-v1"

# ---------------------------------------------------------------------------
# Emotion -> dial mapping. Linear valence(V)/arousal(A) model in the tradition of the
# MARY TTS / Schroeder emotion rules, as extracted and re-validated by
# Burkhardt, Reichel, Eyben & Schuller (2023) "Going Retro..." (ESSV) and Schroeder (2004).
# Each dial is a weighted sum of A and V, following the reported acoustic correlates:
#   * high AROUSAL     -> faster rate, higher intensity, higher F0
#                         (Schroeder: rate=0.5A, volume=0.33A, pitch=0.3A)
#   * positive VALENCE -> faster rate, but LOWER intensity; pitch is the best valence
#                         carrier (Syntact variant: pitch<-valence gave the best valence UAR)
#
# Two-tier weighting so ALL FOUR quadrants differ on every dial, tiered by axis
# (primary dominates, secondary refines):
#   dial   | primary (Tier 1)          | secondary (Tier 2)        | valence sign
#   -------|---------------------------|---------------------------|-------------
#   rate   | arousal (RATE_AROUSAL_W)  | valence (RATE_VALENCE_W)  |  +  (faster)
#   volume | arousal (VOL_AROUSAL_W)   | valence (VOL_VALENCE_W)   |  -  (softer)
#   pitch  | valence (VALENCE_PITCH_W) | arousal (AROUSAL_PITCH_W) |  +  (higher)
#
# Consequence (matches emotion acoustics): Q2 'upset' = LOUDEST + lowest pitch (neg V,
# high A); Q1 'happy' = FASTEST + highest pitch; Q3 'sad' = slow/soft/low; Q4 'calm' =
# softest. Known limitation: a linear V/A model gives 'upset' a LOW pitch, whereas
# hot-anger also has high F0 -- separating anger from fear needs the dominance dimension
# or voice quality (Burkhardt et al. 2023, deferred to a later phase).
# ---------------------------------------------------------------------------

RATE_MIN, RATE_MAX = 0.7, 1.3     # clamp bounds for the rate factor
RATE_AROUSAL_W = 0.20             # A -> rate (primary): fast when excited     (Schroeder 0.5)
RATE_VALENCE_W = 0.08             # V -> rate (secondary, ADDED): positive a touch faster (Schroeder 0.2)

VOL_MIN, VOL_MAX = 0.6, 1.0       # clamp bounds for loudness
VOL_AROUSAL_W = 0.20              # A -> volume (primary): loud when excited   (Schroeder 0.33)
VOL_VALENCE_W = 0.05              # V -> volume (secondary, SUBTRACTED): positive valence = softer

PITCH_MIN, PITCH_MAX = 0.8, 1.2   # clamp bounds for pitch
VALENCE_PITCH_W = 0.22            # V -> pitch (primary channel; Syntact: pitch carries valence)
AROUSAL_PITCH_W = 0.15            # A -> pitch (secondary): higher when excited (Schroeder 0.3)


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def arousal_to_rate(arousal: float) -> float:
    """Arousal-only rate component (primary tier). Monotonic in arousal, clamped."""
    return _clamp(1.0 + RATE_AROUSAL_W * arousal, RATE_MIN, RATE_MAX)


def emotion_to_rate(valence: float, arousal: float) -> float:
    """Rate from BOTH axes: arousal (primary) + a small valence shift (secondary), so
    same-arousal quadrants (Q1/Q2) differ modestly in speed while cross-arousal pairs
    (Q1/Q3) differ strongly. Clamped."""
    return _clamp(1.0 + RATE_AROUSAL_W * arousal + RATE_VALENCE_W * valence, RATE_MIN, RATE_MAX)


def arousal_to_volume(arousal: float) -> float:
    """Arousal-only loudness component (primary tier). Monotonic, clamped.
    (0.8 + 0.2*arousal is identical to the old VOL_MIN + (a+1)/2 * span.)"""
    return _clamp(0.8 + VOL_AROUSAL_W * arousal, VOL_MIN, VOL_MAX)


def emotion_to_volume(valence: float, arousal: float) -> float:
    """Loudness from BOTH axes: arousal (primary, louder when excited) MINUS a small
    valence term (positive valence = lower intensity, per the acoustic correlates), so
    Q2 'upset' is the loudest of the high-arousal pair (anger = high intensity). Clamped."""
    return _clamp(0.8 + VOL_AROUSAL_W * arousal - VOL_VALENCE_W * valence, VOL_MIN, VOL_MAX)


def emotion_to_pitch(valence: float, arousal: float) -> float:
    """Pitch from BOTH axes: valence (PRIMARY channel) + arousal (secondary). Monotonic
    in each axis, clamped, so all four quadrants receive distinct pitches."""
    return _clamp(
        1.0 + AROUSAL_PITCH_W * arousal + VALENCE_PITCH_W * valence,
        PITCH_MIN,
        PITCH_MAX,
    )


@dataclass(frozen=True)
class VoiceParams:
    """Engine-agnostic voice parameters produced by a strategy.

    Carries BOTH the prosodic projection of the emotion (rate/volume/pitch — for engines that
    expose those dials) AND the emotion itself (valence/arousal/intensity/quadrant — for
    engines with NATIVE emotion conditioning, e.g. an expressiveness scalar or a per-quadrant
    reference style).

    Why both (architectural consequence of the Phase-N result): a neutral neural engine
    ignores externally-applied prosody, so emotion must reach it through the engine's own
    conditioning interface. An adapter therefore needs the emotion, not only its prosodic
    encoding. The emotion fields are optional with neutral defaults, so every existing adapter
    and test is unaffected.
    """

    voice_id: str
    rate: float           # speed factor; 1.0 = natural pace     (from arousal)
    volume: float = 1.0   # loudness 0..1                        (from arousal)
    pitch: float = 1.0    # relative voice height; 1.0 = normal  (from arousal+valence)
    valence: float = 0.0    # -1..1  pleasantness  (native-conditioning engines)
    arousal: float = 0.0    # -1..1  activation    (native-conditioning engines)
    intensity: float = 0.0  # 0..1   emotion strength
    quadrant: str = ""      # "Q1".."Q4" — lets an engine select a per-quadrant reference style


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
        # Two-tier: every dial blends both axes (arousal primary for pace/loudness,
        # valence primary for pitch), so all four quadrants are distinct on every dial.
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
