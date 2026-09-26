"""LLM adapter (protected seam #2).

`generate(prompt)` returns a parsed result. Every backend implements the same interface,
so the pipeline does not change when the model does.

ECHO runs one model, `llama3.2:3b`, served locally by Ollama. `OllamaAdapter` reaches it
through Ollama's OpenAI-compatible HTTP endpoint (`http://localhost:11434/v1`); that wire
protocol is the only reason `openai` is a dependency. No OpenAI service is contacted, no
account or key exists (`api_key="ollama"` is a required but ignored placeholder), and no
text leaves the machine. A hosted backend could be added as a new class; none is
implemented or planned, because Chapter 1's aim is a locally deployed system.
"""

from __future__ import annotations

import json
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from contracts import Quadrant

_FENCE = re.compile(r"^```(?:json)?|```$", re.MULTILINE)
_JSON_OBJ = re.compile(r"\{.*\}", re.DOTALL)


@dataclass
class LLMResult:
    reply: str
    self_quadrant: Quadrant | None
    model_id: str
    raw: str = ""
    params: dict = field(default_factory=dict)


def parse_llm_json(text: str) -> tuple[str, Quadrant | None]:
    """Extract (reply, self_quadrant) from a model response.

    Strips code fences and parses the span from the first `{` to the last `}`. A malformed
    response returns the raw text as the reply and None as the quadrant instead of raising.
    """
    cleaned = _FENCE.sub("", text).strip()
    match = _JSON_OBJ.search(cleaned)
    if not match:
        return text.strip(), None
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return text.strip(), None

    reply = str(data.get("reply", "")).strip() or text.strip()
    sq = data.get("self_quadrant")
    quadrant: Quadrant | None = None
    if isinstance(sq, str):
        try:
            quadrant = Quadrant(sq.strip().upper())
        except ValueError:
            quadrant = None
    return reply, quadrant


class LLMAdapter(ABC):
    """Contract shared by every language-model backend."""

    model_id: str = "abstract"

    @abstractmethod
    def generate(self, prompt: str) -> LLMResult: ...


# Cue -> (quadrant, reply); cues match the wording of prompts/q*.txt.
# Replies use real affect words so the mock exercises an independent judge (lexicon),
# not only the legacy self-report path. A placeholder such as "[mock Q1 reply]" has no
# emotional content, so an honest judge would rightly refuse to certify it and the mock
# pipeline would never pass its own gate.
_MOCK_CUES = {
    "HAPPY and ENERGETIC": ("Q1", "That is wonderful, I am delighted and excited."),
    "UPSET and AGITATED": ("Q2", "This is outrageous and unacceptable, I am furious."),
    "SAD and SUBDUED": ("Q3", "I feel lonely and miserable and tired."),
    "CALM and CONTENT": ("Q4", "Everything is calm, peaceful and relaxed."),
}


class MockLLMAdapter(LLMAdapter):
    """Deterministic adapter for tests and offline demos.

    Returns `scripted` (a raw string) if given, else a canned JSON reply for the quadrant
    the prompt asks for.
    """

    model_id = "mock"

    def __init__(self, scripted: str | None = None, model_id: str = "mock") -> None:
        self._scripted = scripted
        self.model_id = model_id

    def generate(self, prompt: str) -> LLMResult:
        if self._scripted is not None:
            raw = self._scripted
        else:
            # Simulates a cooperative model that complies with the requested emotion.
            # Since G6.1 the prompt has no `self_quadrant`, so the cue is the emotion
            # description. `self_quadrant` is still emitted so the legacy L0 judge stays
            # testable; independent judges ignore it.
            q, reply = next((v for k, v in _MOCK_CUES.items() if k in prompt),
                            _MOCK_CUES["HAPPY and ENERGETIC"])
            raw = json.dumps({"reply": reply, "self_quadrant": q})
        reply, quadrant = parse_llm_json(raw)
        return LLMResult(reply=reply, self_quadrant=quadrant, model_id=self.model_id, raw=raw)


class OllamaAdapter(LLMAdapter):
    """Local Ollama via its OpenAI-compatible endpoint; the only live backend."""

    def __init__(
        self,
        host: str,
        model: str,
        *,
        temperature: float = 0.7,
        timeout_s: float = 60.0,
    ) -> None:
        # `openai` is a client for Ollama's OpenAI-compatible protocol here, not a
        # connection to OpenAI. Imported here so tests and offline runs do not need it.
        from openai import OpenAI

        # api_key: Ollama requires the Authorization header and ignores its value.
        self._client = OpenAI(base_url=host, api_key="ollama", timeout=timeout_s)
        self.model_id = model
        self._temperature = temperature
        self._host = host

    def ping(self) -> None:
        """Check that the endpoint is reachable; raise on failure.

        Constructing the client makes no network call, so wrapping __init__ in try/except
        cannot detect an unreachable server: the failure surfaces later, in generate(), as
        a 60-line httpx traceback (observed 2026-08-30 with Ollama not running). Call this
        to fail fast.
        """
        self._client.models.list()

    def generate(self, prompt: str) -> LLMResult:
        resp = self._client.chat.completions.create(
            model=self.model_id,
            messages=[{"role": "user", "content": prompt}],
            temperature=self._temperature,
        )
        raw = resp.choices[0].message.content or ""
        reply, quadrant = parse_llm_json(raw)
        return LLMResult(
            reply=reply,
            self_quadrant=quadrant,
            model_id=self.model_id,
            raw=raw,
            params={"temperature": self._temperature},
        )
