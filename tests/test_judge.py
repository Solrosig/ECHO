import pytest

from contracts import Quadrant
from judge import (
    BlindLLMJudge,
    CascadeJudge,
    LexiconJudge,
    SelfReportJudge,
    load_norms,
    make_judge,
    parse_quadrant,
)
from llm import LLMResult, MockLLMAdapter


def _result(reply="whatever", q=Quadrant.Q1):
    return LLMResult(reply=reply, self_quadrant=q, model_id="mock", raw="")


# --- parsing -----------------------------------------------------------------

def test_parse_quadrant_from_json():
    assert parse_quadrant('{"quadrant": "Q3"}') == Quadrant.Q3


def test_parse_quadrant_from_fenced_json():
    assert parse_quadrant('```json\n{"quadrant": "q2"}\n```') == Quadrant.Q2


def test_parse_quadrant_falls_back_to_bare_token():
    assert parse_quadrant("I think this is Q4, calm and content.") == Quadrant.Q4


def test_parse_quadrant_degrades_to_none():
    assert parse_quadrant("no idea") is None
    assert parse_quadrant("") is None


# --- L0: self-report (legacy, kept only for the before/after experiment) -------

def test_self_report_judge_returns_the_generators_claim():
    j = SelfReportJudge()
    assert j.level == 0
    assert j.judge("text", _result(q=Quadrant.Q2)) == Quadrant.Q2


def test_self_report_judge_has_no_opinion_without_a_result():
    assert SelfReportJudge().judge("text") is None


# --- L1: blind LLM ------------------------------------------------------------

def test_blind_llm_judge_ignores_the_generators_self_report():
    """The whole point of the seam: the judge must not read the answer key.

    The generator claims Q1; the (mock) judge model says Q3. A judge that leaked
    would return Q1.
    """
    judge = BlindLLMJudge(MockLLMAdapter(scripted='{"quadrant": "Q3"}'))
    assert judge.level == 1
    assert judge.judge("some reply", _result(q=Quadrant.Q1)) == Quadrant.Q3


def test_blind_llm_judge_prompt_never_contains_the_target():
    seen = {}

    class Spy(MockLLMAdapter):
        def generate(self, prompt):
            seen["prompt"] = prompt
            return LLMResult(reply="", self_quadrant=None, model_id="spy",
                             raw='{"quadrant": "Q2"}')

    BlindLLMJudge(Spy()).judge("the bus was late again", _result(q=Quadrant.Q4))
    assert "the bus was late again" in seen["prompt"]
    assert "self_quadrant" not in seen["prompt"]


def test_blind_llm_judge_has_no_opinion_on_empty_text():
    assert BlindLLMJudge(MockLLMAdapter()).judge("   ") is None


# --- L2: lexicon --------------------------------------------------------------

@pytest.mark.parametrize("text,expected", [
    ("wonderful, I am delighted and excited", Quadrant.Q1),
    ("this is outrageous and unacceptable, I am furious", Quadrant.Q2),
    ("I feel lonely and miserable and tired", Quadrant.Q3),
    ("everything is calm, peaceful and relaxed", Quadrant.Q4),
])
def test_lexicon_judge_places_obvious_text(text, expected):
    j = LexiconJudge()
    assert j.level == 2
    assert j.judge(text) == expected


def test_lexicon_judge_has_no_opinion_without_recognised_words():
    assert LexiconJudge().judge("the appliance sits on the shelf") is None


def test_lexicon_judge_is_deterministic():
    j = LexiconJudge()
    text = "I am delighted"
    assert j.judge(text) == j.judge(text)


def test_lexicon_score_returns_hits_and_bounded_values():
    v, a, hits = LexiconJudge().score("delighted and excited")
    assert hits == 2
    assert -1.0 <= v <= 1.0 and -1.0 <= a <= 1.0


def test_load_norms_falls_back_when_file_missing():
    assert load_norms("/definitely/not/a/path.csv")  # seed table, not empty


def test_load_norms_reads_a_warriner_format_csv(tmp_path):
    p = tmp_path / "norms.csv"
    p.write_text("word,valence,arousal\nglorious,8.5,6.0\n", encoding="utf-8")
    norms = load_norms(str(p))
    assert norms["glorious"] == (8.5, 6.0)


# --- factory ------------------------------------------------------------------

def test_make_judge_returns_each_level():
    assert make_judge("self-report").level == 0
    assert make_judge("blind-llm", llm=MockLLMAdapter()).level == 1
    assert make_judge("lexicon").level == 2


def test_make_judge_rejects_unknown_and_missing_llm():
    with pytest.raises(ValueError):
        make_judge("telepathy")
    with pytest.raises(ValueError):
        make_judge("blind-llm")

# --- cascade: lexicon first, blinded LLM only on abstention -------------------

def _cascade(scripted='{"quadrant": "Q2"}'):
    return CascadeJudge(LexiconJudge(), BlindLLMJudge(MockLLMAdapter(scripted=scripted)))


def test_cascade_uses_the_lexicon_when_it_has_an_opinion():
    """Independence is preserved wherever the lexicon can actually speak."""
    j = _cascade(scripted='{"quadrant": "Q1"}')      # LLM would disagree
    assert j.judge("I feel lonely and miserable and tired") == Quadrant.Q3
    assert j.judge_id.endswith("[lexicon]")
    assert j.level == 2


def test_cascade_falls_back_only_when_the_lexicon_abstains():
    """Real case from 2026-08-30: 'Thursday already? I'm not ready for it yet.' carries
    no rated vocabulary, the lexicon abstains, and the turn would otherwise fail."""
    j = _cascade(scripted='{"quadrant": "Q3"}')
    assert LexiconJudge().judge("the appliance sits on the shelf") is None
    assert j.judge("the appliance sits on the shelf") == Quadrant.Q3
    assert j.judge_id.endswith("[blind-llm:mock]")
    assert j.level == 1                               # the level ACTUALLY achieved


def test_cascade_records_which_judge_decided_each_time():
    j = _cascade()
    j.judge("everything is calm, peaceful and relaxed")   # lexicon
    j.judge("the appliance sits on the shelf")            # fallback
    assert j.decisions["lexicon"] == 1
    assert j.decisions["blind-llm:mock"] == 1


def test_cascade_returns_none_only_if_both_abstain():
    j = CascadeJudge(LexiconJudge(), BlindLLMJudge(MockLLMAdapter(scripted="no idea")))
    assert j.judge("the appliance sits on the shelf") is None


def test_make_judge_builds_a_cascade_and_needs_an_llm():
    j = make_judge("cascade", llm=MockLLMAdapter())
    assert isinstance(j, CascadeJudge) and j.level == 2
    with pytest.raises(ValueError):
        make_judge("cascade")


def test_self_report_warns_once_when_the_prompt_no_longer_supplies_the_field(capsys):
    """Under prompts-v2 the field is gone, so L0 can only abstain. It must say so."""
    SelfReportJudge._warned = False
    j = SelfReportJudge()
    assert j.judge("text", _result(q=None)) is None
    err = capsys.readouterr().err
    assert "prompts-v2" in err and "self_quadrant" in err
    j.judge("text", _result(q=None))                  # warns once, not per turn
    assert capsys.readouterr().err == ""
