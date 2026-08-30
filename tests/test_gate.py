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


# --- G6: the gate now judges the TEXT, not the generator's claim ---------------

def test_gate_uses_the_judge_not_the_self_report():
    """A blinded judge can reject a reply the generator claimed was on target.

    Under the old L0 behaviour this turn would have passed on the first attempt,
    because the model's self-report was copied from the prompt template.
    """
    from judge import LexiconJudge

    def gen():
        # generator CLAIMS Q1, but the words are plainly Q3
        return LLMResult(reply="I feel lonely and miserable",
                         self_quadrant=Quadrant.Q1, model_id="mock")

    attempts = run_gated(gen, Quadrant.Q1, max_retries=1, judge=LexiconJudge())
    assert all(a.passed is False for a in attempts)
    assert attempts[-1].self_quadrant == Quadrant.Q3       # what the judge actually saw
    assert attempts[-1].accepted is True                    # a turn still yields a reply


def test_gate_records_which_judge_decided():
    from judge import LexiconJudge

    attempts = run_gated(
        lambda: LLMResult(reply="calm and peaceful", self_quadrant=None, model_id="mock"),
        Quadrant.Q4, max_retries=0, judge=LexiconJudge(),
    )
    assert attempts[0].judged_by == "lexicon"
    assert attempts[0].judge_level == 2
    assert attempts[0].passed is True


def test_gate_defaults_to_legacy_self_report_for_existing_callers():
    attempts = run_gated(lambda: _result(Quadrant.Q1), Quadrant.Q1, max_retries=0)
    assert attempts[0].judge_level == 0
    assert attempts[0].judged_by == "self-report"
