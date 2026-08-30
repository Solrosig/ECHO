"""Emotion judge — PROTECTED SEAM #5.

Answers ONE question: *what emotion does this text express?* — and, critically,
answers it **without being told what the text was supposed to express**.

Why this exists
---------------
Until now the coherence gate used the generating model's own `self_quadrant`
field. That was not a judgement: `prompts/q2.txt` specified the output format as
``{"reply": "<your reply>", "self_quadrant": "Q2"}``, so the expected answer was
pre-filled in the template and the model was copying, not assessing. The evidence
is in `echo.db`: 5 turns, 5 attempts, 5 first-attempt passes, 0 retries — the gate
had never rejected anything.

The standing project principle is that **the instrument that produces must not be
the instrument that verifies** (see ROADMAP §4c). This seam is where that applies
to the text channel.

Independence levels (recorded per turn as `judge_level`, so every result declares
how much independence it actually had):

    L0  SelfReportJudge  same model, same context, target visible   — legacy, kept
                         only so the before/after experiment (G6.5) can be run
    L1  BlindLLMJudge    same model, FRESH context, target withheld — leakage gone
    L2  LexiconJudge     affective-norm lexicon, no LLM at all      — different
                         instrument family; the adopted target for reported results
    L3  (future)         a different model family entirely

Refs: Zheng et al. 2023 (self-enhancement bias); Panickssery, Bowman & Feng 2024
(LLM evaluators recognise and favour their own generations); Huang et al. 2024
(intrinsic self-correction fails without external feedback).
"""

from __future__ import annotations

import csv
import json
import sys
import os
import re
from abc import ABC, abstractmethod
from pathlib import Path

from contracts import Quadrant, quadrant_for
from llm import LLMAdapter, LLMResult

JUDGE_PROMPT_VERSION = "judge-v1"

# The judge NEVER sees the target. It sees only the text.
JUDGE_PROMPT = """Read the following spoken reply and judge which emotional quadrant it expresses.

Q1 = happy / energetic (positive feeling, high energy)
Q2 = upset / agitated (negative feeling, high energy)
Q3 = sad / subdued (negative feeling, low energy)
Q4 = calm / content (positive feeling, low energy)

Reply: "{text}"

Answer with ONLY this JSON and nothing else:
{{"quadrant": "<Q1|Q2|Q3|Q4>"}}"""

_QUAD_RE = re.compile(r"\bQ([1-4])\b", re.IGNORECASE)
_FENCE = re.compile(r"^```(?:json)?|```$", re.MULTILINE)
_JSON_OBJ = re.compile(r"\{.*\}", re.DOTALL)
_WORD_RE = re.compile(r"[a-z']+")


def parse_quadrant(text: str) -> Quadrant | None:
    """Pull a quadrant out of a judge response, defensively.

    Tries JSON first (the requested format), then falls back to the first bare
    Q1-Q4 token anywhere in the text. Returns None rather than raising, so a
    malformed judge response degrades to "no opinion" instead of crashing a turn.
    """
    cleaned = _FENCE.sub("", text or "").strip()
    match = _JSON_OBJ.search(cleaned)
    if match:
        try:
            data = json.loads(match.group(0))
            value = data.get("quadrant")
            if isinstance(value, str):
                try:
                    return Quadrant(value.strip().upper())
                except ValueError:
                    pass
        except json.JSONDecodeError:
            pass
    found = _QUAD_RE.search(cleaned)
    return Quadrant(f"Q{found.group(1)}") if found else None


class EmotionJudge(ABC):
    """Contract shared by every emotion judge."""

    judge_id: str = "abstract"
    level: int = -1          # independence level, recorded per turn

    @abstractmethod
    def judge(self, text: str, result: LLMResult | None = None) -> Quadrant | None:
        """Return the quadrant this TEXT expresses, or None if no opinion.

        `result` is offered only for the legacy L0 judge, which reads the
        generator's self-report. Independent judges must ignore it — that is
        precisely what makes them independent.
        """


class SelfReportJudge(EmotionJudge):
    """L0 — the generator's own `self_quadrant`. Kept for comparison ONLY.

    This is the pre-2026-08-23 behaviour. It is retained so that G6.5 can measure
    how far agreement falls when the judge is blinded; it must not be used for a
    reported result.
    """

    judge_id = "self-report"
    level = 0
    _warned = False

    def judge(self, text: str, result: LLMResult | None = None) -> Quadrant | None:
        q = result.self_quadrant if result is not None else None
        if q is None and not SelfReportJudge._warned:
            SelfReportJudge._warned = True
            print(
                "WARNING: the self-report judge found no `self_quadrant` in the model's "
                "reply.\r\n"
                "         Since prompts-v2 (story G6.1) the templates no longer ASK for "
                "that field,\r\n"
                "         so L0 cannot form an opinion and every turn will fail the gate. "
                "This judge\r\n"
                "         is kept only to reproduce the pre-G6 behaviour against "
                "`prompts-v1`.",
                file=sys.stderr,
            )
        return q


class BlindLLMJudge(EmotionJudge):
    """L1 — the same model, asked in a FRESH context, with the target withheld.

    Cheapest real improvement available: no new dependency, no new model, and it
    removes the leakage that made the gate vacuous. Still shares the generator's
    training data and architecture, so its errors remain correlated with the
    generator's — which is why L2 is the target for reported results.
    """

    judge_id = "blind-llm"
    level = 1

    def __init__(self, llm: LLMAdapter) -> None:
        self._llm = llm
        self.judge_id = f"blind-llm:{llm.model_id}"

    def judge(self, text: str, result: LLMResult | None = None) -> Quadrant | None:
        if not (text or "").strip():
            return None
        response = self._llm.generate(JUDGE_PROMPT.format(text=text.strip()))
        # The judge prompt asks for {"quadrant": ...}; parse the RAW response, since
        # `reply`/`self_quadrant` belong to the generation contract, not this one.
        return parse_quadrant(response.raw or response.reply)


def _rescale(value: float) -> float:
    """Warriner-format 1-9 rating -> [-1, 1]. 5 is the neutral midpoint."""
    return max(-1.0, min(1.0, (float(value) - 5.0) / 4.0))


# Coarse placeholder norms so the lexicon judge works offline and in tests.
# NOT the published values: point ECHO_AFFECT_NORMS at a real Warriner-format CSV
# (word,valence,arousal on the 1-9 scale) before reporting any result from L2.
_SEED_NORMS: dict[str, tuple[float, float]] = {
    "happy": (8.2, 6.0), "great": (7.5, 5.8), "wonderful": (8.3, 6.2), "love": (8.0, 6.4),
    "excited": (7.4, 7.6), "yay": (7.8, 7.0), "brilliant": (7.9, 6.3), "delighted": (8.1, 6.5),
    "angry": (2.5, 7.2), "furious": (2.0, 7.9), "hate": (1.8, 6.9), "annoyed": (2.8, 6.2),
    "unacceptable": (2.3, 6.4), "ridiculous": (2.9, 6.1), "outrageous": (2.2, 7.1),
    "sad": (2.1, 3.2), "sorry": (3.0, 3.6), "lonely": (2.2, 3.4), "tired": (3.2, 2.6),
    "disappointed": (2.6, 3.8), "miserable": (1.9, 3.5), "quiet": (5.4, 2.4),
    "calm": (7.0, 2.2), "peaceful": (7.6, 2.0), "fine": (6.4, 3.4), "gentle": (7.2, 2.8),
    "relaxed": (7.7, 2.1), "content": (7.3, 2.9), "steady": (6.2, 3.0), "okay": (6.0, 3.5),
}


def load_norms(path: str | None = None) -> dict[str, tuple[float, float]]:
    """Load word -> (valence, arousal) on the 1-9 rating scale.

    Reads a Warriner-format CSV when one is configured and present; otherwise
    returns the seed table above, so the judge is always constructible offline.
    """
    path = path or os.getenv("ECHO_AFFECT_NORMS", "")
    if not path or not Path(path).exists():
        return dict(_SEED_NORMS)
    norms: dict[str, tuple[float, float]] = {}
    with open(path, newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            word = (row.get("word") or row.get("Word") or "").strip().lower()
            try:
                valence = float(row.get("valence") or row["V.Mean.Sum"])
                arousal = float(row.get("arousal") or row["A.Mean.Sum"])
            except (KeyError, TypeError, ValueError):
                continue
            if word:
                norms[word] = (valence, arousal)
    return norms or dict(_SEED_NORMS)


class LexiconJudge(EmotionJudge):
    """L2 — affective-norm lexicon. Deterministic, offline, and NOT a language model.

    Averages the valence and arousal norms of the words it recognises and maps the
    result onto a quadrant with the same rule the contracts use. Shares no
    machinery with the generator, so agreement between the two is triangulation
    rather than a second opinion from the same source.

    Known weakness, stated rather than hidden: word-level aggregation ignores
    negation, intensification and irony, so it is least reliable exactly where
    language is most subtle. That is why disagreement is logged as data rather
    than resolved in favour of either party.
    """

    judge_id = "lexicon"
    level = 2

    def __init__(self, norms: dict[str, tuple[float, float]] | None = None,
                 min_hits: int = 1) -> None:
        self._norms = norms if norms is not None else load_norms()
        self._min_hits = min_hits

    def score(self, text: str) -> tuple[float, float, int]:
        """Return (valence, arousal, hits) in [-1, 1]; hits = words recognised."""
        vals, ars = [], []
        for word in _WORD_RE.findall((text or "").lower()):
            hit = self._norms.get(word)
            if hit:
                vals.append(_rescale(hit[0]))
                ars.append(_rescale(hit[1]))
        if not vals:
            return 0.0, 0.0, 0
        return sum(vals) / len(vals), sum(ars) / len(ars), len(vals)

    def judge(self, text: str, result: LLMResult | None = None) -> Quadrant | None:
        valence, arousal, hits = self.score(text)
        if hits < self._min_hits:
            return None          # no opinion beats a fabricated one
        return quadrant_for(valence, arousal)


class CascadeJudge(EmotionJudge):
    """Primary judge first; fall back to a second one only when the primary ABSTAINS.

    Why this exists (evidence, 2026-08-30). The lexicon judge is the independent
    instrument the project wants, but it can only speak about words it has ratings for.
    On the first real run it abstained on three of four replies with the placeholder
    table, and still abstains on roughly one in eight with the full Warriner norms —
    "Thursday already? I'm not ready for it yet." carries little rated vocabulary. An
    abstention fails the gate, so those turns burn the whole retry budget and are then
    accepted anyway: the strictness costs latency without buying correctness.

    Meanwhile the blinded LLM judge answered correctly on every quadrant the lexicon went
    silent on. Cascading keeps L2 independence wherever the lexicon HAS something to say,
    and gets an answer from L1 where it does not.

    `judge_id` and `level` are updated after each decision to name the judge that actually
    decided, so the provenance row records the independence level genuinely achieved on
    that attempt rather than the best case.
    """

    def __init__(self, primary: EmotionJudge, fallback: EmotionJudge) -> None:
        self._primary = primary
        self._fallback = fallback
        self._name = f"cascade:{primary.judge_id}->{fallback.judge_id}"
        self.judge_id = self._name
        self.level = primary.level
        self.decisions: dict[str, int] = {primary.judge_id: 0, fallback.judge_id: 0}

    def judge(self, text: str, result: LLMResult | None = None) -> Quadrant | None:
        quadrant = self._primary.judge(text, result)
        decider = self._primary if quadrant is not None else self._fallback
        if quadrant is None:
            quadrant = self._fallback.judge(text, result)
        # Report the judge that actually decided — gate.py reads these AFTER judge().
        self.judge_id = f"{self._name}[{decider.judge_id}]"
        self.level = decider.level
        self.decisions[decider.judge_id] = self.decisions.get(decider.judge_id, 0) + 1
        return quadrant


_JUDGES = {"self-report": 0, "blind-llm": 1, "lexicon": 2, "cascade": 2}


def make_judge(kind: str, *, llm: LLMAdapter | None = None,
               norms_path: str | None = None) -> EmotionJudge:
    """Factory so the judge is configuration, not a code change.

    kind: self-report (L0) | blind-llm (L1) | lexicon (L2) | cascade (L2 with L1 fallback)
    """
    kind = (kind or "").strip().lower()
    if kind == "self-report":
        return SelfReportJudge()
    if kind == "blind-llm":
        if llm is None:
            raise ValueError("blind-llm judge needs an LLMAdapter")
        return BlindLLMJudge(llm)
    if kind == "lexicon":
        return LexiconJudge(load_norms(norms_path))
    if kind == "cascade":
        if llm is None:
            raise ValueError("cascade judge needs an LLMAdapter for its fallback")
        return CascadeJudge(LexiconJudge(load_norms(norms_path)), BlindLLMJudge(llm))
    raise ValueError(f"unknown judge {kind!r}; expected one of {sorted(_JUDGES)}")
