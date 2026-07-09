from llm import LLMResult
from contracts import Quadrant
from gate import coheres, run_gated


def _result(q):
    return LLMResult(reply=f"reply-{q}", self_quadrant=q, model_id="mock")


def test_coheres_match_and_mismatch():
    assert coheres(Quadrant.Q1, Quadrant.Q1) is True
    assert coheres(Quadrant.Q1, Quadrant.Q2) is False
    assert coheres(Quadrant.Q1, None) is False


def test_first_attempt_passes():
    attempts = run_gated(lambda: _result(Quadrant.Q1), Quadrant.Q1, max_retries=2)
    assert len(attempts) == 1
    assert attempts[0].passed and attempts[0].accepted


def test_mismatch_then_pass():
    seq = [_result(Quadrant.Q3), _result(Quadrant.Q1)]
    it = iter(seq)
    attempts = run_gated(lambda: next(it), Quadrant.Q1, max_retries=2)
    assert len(attempts) == 2
    assert attempts[0].passed is False and attempts[0].accepted is False
    assert attempts[1].passed and attempts[1].accepted


def test_retries_exhausted_accepts_last():
    attempts = run_gated(lambda: _result(Quadrant.Q3), Quadrant.Q1, max_retries=2)
    assert len(attempts) == 3  # never exceeds first + max_retries
    assert all(a.passed is False for a in attempts)
    assert attempts[-1].accepted is True
    assert sum(a.accepted for a in attempts) == 1
