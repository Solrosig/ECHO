"""Coherence gate.

Generate a reply, ask a JUDGE what emotion it expresses, retry on mismatch.

CHANGED 2026-08-23 (story G6). The gate previously used the generating model's
own `self_quadrant` field, but the prompt templates pre-filled the expected value
(`{"reply": ..., "self_quadrant": "Q2"}`), so the model was copying an answer key
rather than judging. `echo.db` showed the consequence: 5 turns, 5 first-attempt
passes, 0 retries — the gate had never rejected anything.

The judgement now comes from an `EmotionJudge` (protected seam #5) that sees the
generated TEXT and not the target. The independence level actually used is
recorded per turn, so every result declares how much independence it had.

The pure decision (`coheres`) stays separated from the retry loop (`run_gated`)
so both remain easy to test. Every attempt is still recorded — pre-gate, each
retry, and the accepted one — for later analysis.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from contracts import Quadrant
from judge import EmotionJudge, SelfReportJudge
from llm import LLMResult


def coheres(target: Quadrant, detected: Quadrant | None) -> bool:
    """Pass when the judged quadrant matches the target."""
    return detected is not None and detected == target


@dataclass
class Attempt:
    index: int
    reply: str
    self_quadrant: Quadrant | None   # what the JUDGE returned (name kept for schema compat)
    passed: bool
    accepted: bool = False
    raw: str = ""
    judged_by: str = ""              # which judge produced it
    judge_level: int = -1            # 0 self-report | 1 blind LLM | 2 lexicon


def run_gated(
    generate_fn: Callable[[], LLMResult],
    target: Quadrant,
    *,
    max_retries: int = 2,
    judge: EmotionJudge | None = None,
) -> list[Attempt]:
    """Generate, judge, retry on mismatch (bounded).

    Returns every attempt in order. Exactly one attempt is flagged `accepted`:
    the first that passes, or - if none pass - the last one, so a turn always
    yields a usable reply for the demo.

    `judge` defaults to `SelfReportJudge` (L0) purely so existing callers keep
    working unchanged; it is NOT a defensible setting for a reported result.
    """
    judge = judge or SelfReportJudge()
    attempts: list[Attempt] = []
    total = max_retries + 1  # first try + retries
    for i in range(total):
        result = generate_fn()
        detected = judge.judge(result.reply, result)
        passed = coheres(target, detected)
        attempts.append(
            Attempt(
                index=i,
                reply=result.reply,
                self_quadrant=detected,
                passed=passed,
                raw=result.raw,
                judged_by=judge.judge_id,
                judge_level=judge.level,
            )
        )
        if passed:
            attempts[-1].accepted = True
            return attempts

    attempts[-1].accepted = True  # none passed: accept the last (best effort)
    return attempts
