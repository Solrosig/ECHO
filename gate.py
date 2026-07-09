"""Coherence gate.

MVP coherence signal is the model's OWN self-assessment (JSON `self_quadrant`),
not a separate classifier — this keeps heavy ML off the critical path. The pure
decision (`coheres`) is separated from the retry loop (`run_gated`) so both are
easy to test.

Every attempt is recorded (pre-gate + each retry + accepted) for later analysis.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from llm import LLMResult
from contracts import Quadrant


def coheres(target: Quadrant, detected: Quadrant | None) -> bool:
    """Pass when the reply's self-assessed quadrant matches the target."""
    return detected is not None and detected == target


@dataclass
class Attempt:
    index: int
    reply: str
    self_quadrant: Quadrant | None
    passed: bool
    accepted: bool = False
    raw: str = ""


def run_gated(
    generate_fn: Callable[[], LLMResult],
    target: Quadrant,
    *,
    max_retries: int = 2,
) -> list[Attempt]:
    """Generate, check coherence, retry on mismatch (bounded).

    Returns every attempt in order. Exactly one attempt is flagged `accepted`:
    the first that passes, or — if none pass — the last one, so a turn always
    yields a usable reply for the demo.
    """
    attempts: list[Attempt] = []
    total = max_retries + 1  # first try + retries
    for i in range(total):
        result = generate_fn()
        passed = coheres(target, result.self_quadrant)
        attempts.append(
            Attempt(
                index=i,
                reply=result.reply,
                self_quadrant=result.self_quadrant,
                passed=passed,
                raw=result.raw,
            )
        )
        if passed:
            attempts[-1].accepted = True
            return attempts

    attempts[-1].accepted = True  # none passed: accept the last (best effort)
    return attempts
