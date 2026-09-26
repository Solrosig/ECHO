"""Coherence gate: generate a reply, ask a judge what emotion it expresses, retry on mismatch.

Changed 2026-08-23 (story G6). Until then the gate used the generating model's own
`self_quadrant`, but the prompt templates pre-filled it
(`{"reply": ..., "self_quadrant": "Q2"}`), so the model copied an answer key. `echo.db`
showed 5 turns, 5 first-attempt passes, 0 retries: the gate had never rejected anything.
The judgement now comes from an `EmotionJudge` (protected seam #5) that sees the
generated text, not the target, and the independence level used is recorded per turn.

The pure decision (`coheres`) is separate from the retry loop (`run_gated`) so both are
easy to test. Every attempt (first, retries, accepted) is kept for later analysis.
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
    self_quadrant: Quadrant | None   # the judge's verdict (name kept for schema compat)
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
    """Generate, judge, retry on mismatch (at most `max_retries` times).

    Returns every attempt in order. Exactly one is flagged `accepted`: the first
    that passes, or the last if none pass, so a turn always yields a usable reply.

    `judge` defaults to `SelfReportJudge` (L0) only so existing callers keep
    working; it is not defensible for a reported result.
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
