import json
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from types import SimpleNamespace

import pytest

from contracts import Quadrant
from gate_service import RequestError, build_judge, gated_reply, make_handler
from judge import EmotionJudge
from llm import LLMResult

MESSAGES = [
    {"role": "system", "content": "Keep the requested tone."},
    {"role": "user", "content": "The meeting was moved to a different room."},
]


class ScriptedJudge(EmotionJudge):
    judge_id = "scripted"
    level = 2

    def __init__(self, verdicts):
        self._verdicts = iter(verdicts)

    def judge(self, text, result=None):
        return next(self._verdicts)


def recording_chat(calls):
    def chat(messages, settings):
        calls.append(dict(settings))
        return LLMResult(reply=f"reply {len(calls)}", self_quadrant=None, model_id=settings["model"])

    return chat


def payload(**overrides):
    return {"emotion": "happy", "messages": MESSAGES, "model": "llama3.2:3b", **overrides}


def run(request, verdicts, calls):
    return gated_reply(request, chat=recording_chat(calls), judge=ScriptedJudge(verdicts), default_model="llama3.2:3b")


def test_first_attempt_passes_with_the_base_seed():
    calls = []
    out = run(payload(), [Quadrant.Q1], calls)
    assert out["text"] == "reply 1" and out["passed"] is True and out["gate"] == "on"
    assert [c["seed"] for c in calls] == [666]
    assert out["attempts"] == [{"index": 0, "seed": 666, "reply": "reply 1", "judged": "Q1", "passed": True,
                                "accepted": True, "judged_by": "scripted", "judge_level": 2}]


def test_each_retry_uses_its_own_seed_until_the_judge_agrees():
    calls = []
    out = run(payload(emotion="sad"), [Quadrant.Q4, Quadrant.Q3], calls)
    assert [c["seed"] for c in calls] == [666, 667]
    assert out["text"] == "reply 2" and out["target"] == "Q3"
    assert [a["passed"] for a in out["attempts"]] == [False, True]


def test_three_misses_accept_the_last_reply_as_best_effort():
    calls = []
    out = run(payload(emotion="calm"), [None, Quadrant.Q3, Quadrant.Q1], calls)
    assert [c["seed"] for c in calls] == [666, 667, 668]
    assert out["text"] == "reply 3" and out["passed"] is False
    assert [a["accepted"] for a in out["attempts"]] == [False, False, True]


def test_settings_pass_through_and_a_missing_model_uses_the_configured_default():
    calls = []
    request = payload(seed=10, temperature=0.2, max_tokens=90)
    request.pop("model")
    run(request, [Quadrant.Q1], calls)
    assert calls == [{"model": "llama3.2:3b", "seed": 10, "temperature": 0.2, "max_tokens": 90}]


def test_the_service_judge_uses_the_configured_affect_norms(tmp_path):
    norms = tmp_path / "norms.csv"
    norms.write_text("word,valence,arousal\nzorbling,8.0,8.0\n", encoding="utf-8")
    cfg = SimpleNamespace(judge="lexicon", affect_norms=str(norms), ollama_host="http://127.0.0.1:9/v1",
                          ollama_model="llama3.2:3b", llm_temperature=0.7, llm_timeout_s=1.0)
    # Only the configured file rates this word; the placeholder table would abstain.
    assert build_judge(cfg).judge("zorbling") == Quadrant.Q1


@pytest.mark.parametrize("bad", [
    "not an object",
    {"emotion": "angry", "messages": MESSAGES},
    {"emotion": "happy", "messages": []},
    {"emotion": "happy", "messages": [{"role": "user", "content": 3}]},
    {"emotion": "happy", "messages": MESSAGES[:1]},
    {"emotion": "happy", "messages": MESSAGES, "seed": "666"},
    {"emotion": "happy", "messages": MESSAGES, "temperature": True},
])
def test_invalid_requests_are_rejected(bad):
    with pytest.raises(RequestError):
        run(bad, [], [])


@pytest.fixture
def server():
    def service(request):
        if request == "boom":
            raise RuntimeError("model unavailable")
        return run(request, [Quadrant.Q2], [])

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(service))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()
    httpd.server_close()


OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def post(url, data):
    request = urllib.request.Request(url, data=data, method="POST", headers={"Content-Type": "application/json"})
    try:
        with OPENER.open(request, timeout=10) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read())


def test_http_round_trip_and_error_codes(server):
    status, body = post(server + "/v1/gated-reply", json.dumps(payload(emotion="upset")).encode())
    assert status == 200 and body["passed"] is True and body["attempts"][0]["judged"] == "Q2"
    assert post(server + "/v1/gated-reply", b"{not json")[0] == 400
    assert post(server + "/v1/gated-reply", json.dumps({"emotion": "angry"}).encode())[0] == 400
    assert post(server + "/v1/gated-reply", json.dumps("boom").encode())[0] == 502
    assert post(server + "/v1/other", b"{}")[0] == 404
    with OPENER.open(server + "/health", timeout=10) as response:
        assert json.loads(response.read()) == {"ok": True, "gate": "on"}
