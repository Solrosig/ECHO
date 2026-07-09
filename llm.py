"""LLM adapter — PROTECTED SEAM #2.

`generate(prompt)` returns a parsed result. The local OllamaAdapter and a future
commercial OpenAIAdapter share this interface, so the pipeline never changes when
the model does.
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

    Defensive: strips code fences, finds the first JSON object, and degrades
    gracefully — a malformed response keeps the raw text as the reply and returns
    a null quadrant instead of crashing.
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


class MockLLMAdapter(LLMAdapter):
    """Deterministic adapter for tests and offline demos.

    Returns whatever `scripted` provides (a raw string), or a canned JSON reply
    echoing the requested quadrant if none is scripted.
    """

    model_id = "mock"

    def __init__(self, scripted: str | None = None, model_id: str = "mock") -> None:
        self._scripted = scripted
        self.model_id = model_id

    def generate(self, prompt: str) -> LLMResult:
        if self._scripted is not None:
            raw = self._scripted
        else:
            m = re.search(r'"self_quadrant":\s*"(Q[1-4])"', prompt)
            q = m.group(1) if m else "Q1"
            raw = json.dumps({"reply": f"[mock {q} reply]", "self_quadrant": q})
        reply, quadrant = parse_llm_json(raw)
        return LLMResult(reply=reply, self_quadrant=quadrant, model_id=self.model_id, raw=raw)


class OllamaAdapter(LLMAdapter):
    """Local Ollama via its OpenAI-compatible endpoint."""

    def __init__(
        self,
        host: str,
        model: str,
        *,
        temperature: float = 0.7,
        timeout_s: float = 60.0,
    ) -> None:
        # Imported here so tests/offline runs never need the openai package.
        from openai import OpenAI

        self._client = OpenAI(base_url=host, api_key="ollama", timeout=timeout_s)
        self.model_id = model
        self._temperature = temperature

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
