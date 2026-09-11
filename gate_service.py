"""Coherence-gate service for the standalone conversation: option A, OFF by default.

Since 2026-09-11 the standalone web server asks local Ollama (`llama3.2:3b`) for each conversation
reply directly: that is option B, `ECHO_COHERENCE_GATE=off`. Setting `ECHO_COHERENCE_GATE=on` on
the web server sends the same request here instead, and this service wraps it in ECHO's coherence
gate: `gate.run_gated` with the configured `EmotionJudge` (`ECHO_JUDGE`, default `cascade`). The
judge never sees the target; a mismatch is regenerated, at most twice, and the last attempt is
accepted as best effort. Every attempt is returned.

Each attempt uses its own seed. The standalone fixes seed 666, and a fixed seed would return the
same reply on every retry, so attempt i uses seed + i and reports it.

Run:  python gate_service.py    (listens on ECHO_GATE_HOST:ECHO_GATE_PORT, default 127.0.0.1:8790)
"""

from __future__ import annotations

import json
import os
import threading
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from contracts import Quadrant
from gate import run_gated
from judge import EmotionJudge
from llm import LLMResult

EMOTION_QUADRANT = {"happy": Quadrant.Q1, "upset": Quadrant.Q2, "sad": Quadrant.Q3, "calm": Quadrant.Q4}
MAX_BODY_BYTES = 64 * 1024
MAX_RETRIES = 2

ChatFn = Callable[[list, dict], LLMResult]


class RequestError(ValueError):
    """A client error, answered with HTTP 400."""


def _settings(payload: object, default_model: str) -> tuple[list, Quadrant, dict]:
    if not isinstance(payload, dict):
        raise RequestError("Send a JSON object.")
    emotion = payload.get("emotion")
    if emotion not in EMOTION_QUADRANT:
        raise RequestError("Choose an emotion: happy, upset, sad or calm.")
    messages = payload.get("messages")
    well_formed = (
        isinstance(messages, list) and 0 < len(messages) <= 20
        and all(isinstance(m, dict) and m.get("role") in {"system", "user", "assistant"}
                and isinstance(m.get("content"), str) for m in messages)
    )
    if not well_formed or messages[-1]["role"] != "user":
        raise RequestError("Send the conversation as role/content messages ending with the user's message.")
    model = payload.get("model") or default_model
    seed, temperature, max_tokens = payload.get("seed", 666), payload.get("temperature", 0.7), payload.get("max_tokens", 150)
    if not isinstance(model, str) or not all(isinstance(v, int) and not isinstance(v, bool) for v in (seed, max_tokens)) \
            or not isinstance(temperature, (int, float)) or isinstance(temperature, bool):
        raise RequestError("model must be text, seed and max_tokens integers, temperature a number.")
    return messages, EMOTION_QUADRANT[emotion], {"model": model, "seed": seed, "temperature": float(temperature),
                                                 "max_tokens": max_tokens}


def gated_reply(payload: object, *, chat: ChatFn, judge: EmotionJudge, default_model: str,
                max_retries: int = MAX_RETRIES) -> dict:
    """Generate a reply through the coherence gate and report every attempt."""
    messages, target, settings = _settings(payload, default_model)
    seeds = [settings["seed"] + i for i in range(max_retries + 1)]
    next_seed = iter(seeds)
    attempts = run_gated(lambda: chat(messages, {**settings, "seed": next(next_seed)}),
                         target, max_retries=max_retries, judge=judge)
    accepted = next(a for a in attempts if a.accepted)
    return {
        "text": accepted.reply,
        "gate": "on",
        "target": target.value,
        "passed": accepted.passed,
        "attempts": [
            {"index": a.index, "seed": seeds[a.index], "reply": a.reply,
             "judged": a.self_quadrant.value if a.self_quadrant else None,
             "passed": a.passed, "accepted": a.accepted, "judged_by": a.judged_by, "judge_level": a.judge_level}
            for a in attempts
        ],
    }


def ollama_chat(host: str, timeout_s: float) -> ChatFn:
    """The same chat request the web server sends under option B, to Ollama's OpenAI-compatible endpoint."""
    from openai import OpenAI  # a client for Ollama's local wire protocol; no OpenAI service is contacted

    client = OpenAI(base_url=host, api_key="ollama", timeout=timeout_s)

    def chat(messages: list, settings: dict) -> LLMResult:
        resp = client.chat.completions.create(model=settings["model"], messages=messages, seed=settings["seed"],
                                              temperature=settings["temperature"], max_tokens=settings["max_tokens"])
        choice = resp.choices[0]
        text = (choice.message.content or "").strip()
        if not text or choice.finish_reason == "length":
            raise RuntimeError("the reply was empty or incomplete")
        return LLMResult(reply=text, self_quadrant=None, model_id=settings["model"], raw=text, params=dict(settings))

    return chat


def make_handler(service: Callable[[object], dict]) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        server_version = "EchoCoherenceGate/1"

        def _send(self, status: int, body: dict) -> None:
            data = json.dumps(body).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self) -> None:
            if self.path == "/health":
                self._send(200, {"ok": True, "gate": "on"})
            else:
                self._send(404, {"error": "Not found."})

        def do_POST(self) -> None:
            try:
                length = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                length = -1
            if not 0 <= length <= MAX_BODY_BYTES:
                self.close_connection = True
                self._send(413 if length > MAX_BODY_BYTES else 400, {"error": "Send a JSON body of at most 64 KB."})
                return
            # Read the body before answering anything: replying with unread request data makes Windows reset the connection.
            raw = self.rfile.read(length)
            if self.path != "/v1/gated-reply":
                self._send(404, {"error": "Not found."})
                return
            try:
                payload = json.loads(raw or b"null")
            except ValueError:
                self._send(400, {"error": "Send valid JSON."})
                return
            try:
                self._send(200, service(payload))
            except RequestError as error:
                self._send(400, {"error": str(error)})
            except Exception as error:  # the model or the judge failed; the web server reports it as unavailable
                self._send(502, {"error": f"The gated reply could not be generated: {error}"})

        def log_message(self, *args: object) -> None:
            pass

    return Handler


def build_judge(cfg) -> EmotionJudge:
    """The configured judge with the configured affect norms, built as demo.py builds it.

    Without `norms_path` the lexicon silently falls back to its 30-word placeholder table, and most replies are
    then decided by the blind-LLM fallback while the provenance still says cascade.
    """
    from judge import make_judge
    from llm import OllamaAdapter

    llm = OllamaAdapter(cfg.ollama_host, cfg.ollama_model, temperature=cfg.llm_temperature, timeout_s=cfg.llm_timeout_s)
    return make_judge(cfg.judge, llm=llm, norms_path=cfg.affect_norms or None)


def main() -> None:
    from config import load_config

    cfg = load_config()
    judge = build_judge(cfg)
    chat = ollama_chat(cfg.ollama_host, cfg.llm_timeout_s)
    lock = threading.Lock()  # one generation at a time: the cascade judge records its last decision on itself

    def service(payload: object) -> dict:
        with lock:
            return gated_reply(payload, chat=chat, judge=judge, default_model=cfg.ollama_model)

    host, port = os.getenv("ECHO_GATE_HOST", "127.0.0.1"), int(os.getenv("ECHO_GATE_PORT", "8790"))
    server = ThreadingHTTPServer((host, port), make_handler(service))
    print(f"ECHO coherence gate listening on http://{host}:{port} (judge: {cfg.judge}, affect norms: {cfg.affect_norms}). "
          "Stop with Ctrl+C.")
    server.serve_forever()


if __name__ == "__main__":
    main()
