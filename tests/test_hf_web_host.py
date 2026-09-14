"""The Space's hosting helpers: model threads within the container's CPU limit, a model start that is tried again, and
server voices on the owner's quota."""

import asyncio
import hashlib
import importlib.util
import subprocess
import sys
import urllib.error
from pathlib import Path

import pytest

HF = Path(__file__).resolve().parents[1] / "standalone" / "deployment" / "huggingface"
sys.path.insert(0, str(HF))
_spec = importlib.util.spec_from_file_location("web_host", HF / "web_host.py")
web_host = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(web_host)

ORIGIN = "https://solrosig-echo-tts.hf.space"


def cgroup(root: Path, files: dict[str, str]) -> Path:
    for name, text in files.items():
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_text(text)
    return root


@pytest.mark.parametrize(
    ("files", "limit"),
    [
        ({"cpu.max": "200000 100000\n"}, 2),
        ({"cpu.max": "150000 100000\n"}, 1),
        ({"cpu.max": "max 100000\n"}, None),
        ({"cpu/cpu.cfs_quota_us": "400000\n", "cpu/cpu.cfs_period_us": "100000\n"}, 4),
        ({"cpu/cpu.cfs_quota_us": "-1\n", "cpu/cpu.cfs_period_us": "100000\n"}, None),
        ({}, None),
    ],
)
def test_the_cpu_limit_comes_from_the_cgroup_quota(tmp_path, files, limit):
    assert web_host.cpu_limit(cgroup(tmp_path, files)) == limit


def test_the_model_uses_the_container_limit_not_the_host_cores(tmp_path):
    root = cgroup(tmp_path, {"cpu.max": "200000 100000\n"})
    assert web_host.ollama_threads({}, root, cores=192) == 2
    wide = cgroup(tmp_path / "wide", {"cpu.max": "3200000 100000\n"})
    assert web_host.ollama_threads({}, wide, cores=8) == 8
    assert web_host.ollama_threads({}, tmp_path / "no-quota", cores=192) is None


def test_the_author_can_set_the_thread_count(tmp_path):
    root = cgroup(tmp_path, {"cpu.max": "200000 100000\n"})
    assert web_host.ollama_threads({"ECHO_OLLAMA_THREADS": " 6 "}, root, cores=192) == 6
    for wrong in ("0", "many", "-2"):
        with pytest.raises(RuntimeError, match="ECHO_OLLAMA_THREADS"):
            web_host.ollama_threads({"ECHO_OLLAMA_THREADS": wrong}, root, cores=192)


def test_the_thread_count_is_a_parameter_of_a_named_copy_of_the_verified_build():
    assert web_host.ollama_model(16) == "llama3.2:3b-t16"
    assert web_host.ollama_model(None) == web_host.OLLAMA_MODEL == "llama3.2:3b"


def test_ollama_gets_its_own_folders_and_never_the_owner_token(tmp_path, monkeypatch):
    monkeypatch.setenv("ECHO_ZEROGPU_TOKEN", "hf_owner_fixture")
    monkeypatch.delenv("LLAMA_ARG_REPACK", raising=False)
    env = web_host.ollama_environment(tmp_path)
    assert env["OLLAMA_MODELS"] == str(tmp_path / "models")
    assert env["HOME"] == str(tmp_path / "home")
    assert "ECHO_ZEROGPU_TOKEN" not in env
    assert env["LLAMA_ARG_REPACK"] == "0"
    monkeypatch.setenv("LLAMA_ARG_REPACK", "1")
    assert web_host.ollama_environment(tmp_path)["LLAMA_ARG_REPACK"] == "1"


class ExitedProcess:
    def __init__(self, code):
        self.code = code

    def wait(self):
        return self.code


class RunningProcess:
    def __init__(self):
        self.calls = []

    def poll(self):
        return None

    def terminate(self):
        self.calls.append("terminate")

    def wait(self, timeout=None):
        self.calls.append("wait")
        return 0


def supervise(outcomes, clock_times=()):
    """Run the model supervisor over scripted start outcomes and return its waits. It
    returns once a start is refused, so each script ends with StartRefused."""
    outcomes, times, slept = list(outcomes), iter(clock_times), []

    def start(cache, threads):
        outcome = outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    web_host.run_embedded_ollama(
        16, start=start, sleep=slept.append, clock=lambda: next(times)
    )
    assert not outcomes
    return slept


def test_a_failed_model_start_is_tried_again(capsys):
    # 2026-09-14: one HTTP 504 while downloading Ollama ended replies for a whole run.
    gateway = urllib.error.HTTPError(
        "https://github.com", 504, "Gateway Time-out", {}, None
    )
    stop = web_host.StartRefused("end of the test")
    assert supervise([gateway, RuntimeError("Ollama did not start"), stop]) == [15, 30]
    log = capsys.readouterr().out
    assert "did not start (attempt 1): HTTP Error 504: Gateway Time-out." in log
    assert "Trying again in 15 s." in log and "(attempt 2)" in log
    assert "Conversation replies unavailable: end of the test" in log


def test_the_waits_between_failed_starts_grow_to_five_minutes():
    failures = [RuntimeError("Ollama stopped during startup")] * 7
    stop = web_host.StartRefused("end of the test")
    assert supervise([*failures, stop]) == [15, 30, 60, 120, 300, 300, 300]


def test_an_ollama_that_stops_is_started_again(capsys):
    # After a long run the waits start again from 15 s; a quick exit counts as a failure.
    stop = web_host.StartRefused("end of the test")
    runs = [ExitedProcess(137), ExitedProcess(1), stop]
    assert supervise(runs, clock_times=[0, 3600, 4000, 4005]) == [15, 30]
    log = capsys.readouterr().out
    assert "exit code 137; starting the conversation model again in 15 s." in log


def test_a_refused_start_stops_ollama_and_is_not_tried_again(monkeypatch, capsys):
    process = RunningProcess()
    monkeypatch.setattr(web_host, "OLLAMA_PROCESS", process)
    refused = web_host.StartRefused("llama3.2:3b is build 0000, not the tested one")
    assert supervise([refused]) == []
    assert process.calls == ["terminate", "wait"]
    log = capsys.readouterr().out
    assert "Conversation replies unavailable: llama3.2:3b is build 0000" in log


def test_a_changed_ollama_download_is_refused_and_removed(tmp_path, monkeypatch):
    def download(url, target):
        Path(target).write_bytes(b"not the pinned runtime")

    monkeypatch.setattr(web_host.urllib.request, "urlretrieve", download)
    with pytest.raises(web_host.StartRefused, match="checksum mismatch"):
        web_host.start_embedded_ollama(tmp_path, 16)
    assert list(tmp_path.iterdir()) == []


def test_an_interrupted_unpacking_leaves_no_half_runtime(tmp_path, monkeypatch):
    data = b"pinned runtime fixture"

    def download(url, target):
        Path(target).write_bytes(data)

    def interrupted(command, check):
        (Path(command[-1]) / "bin").mkdir(parents=True)
        (Path(command[-1]) / "bin" / "ollama").write_bytes(b"half")
        raise subprocess.CalledProcessError(2, command)

    monkeypatch.setattr(web_host, "OLLAMA_SHA", hashlib.sha256(data).hexdigest())
    monkeypatch.setattr(web_host.urllib.request, "urlretrieve", download)
    monkeypatch.setattr(web_host.subprocess, "run", interrupted)
    with pytest.raises(subprocess.CalledProcessError):
        web_host.start_embedded_ollama(tmp_path, 16)
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize(
    ("text", "seconds"),
    [("", 25), (None, 25), ("x" * 40, 29), ("x" * 350, 60), ("x" * 2000, 60)],
)
def test_a_voice_reserves_gpu_time_by_text_length(text, seconds):
    assert web_host.voice_gpu_seconds(text, "styletts2", "calm", "preset") == seconds


def test_the_owner_token_counts_only_on_hugging_face():
    space = {"SPACE_ID": "solrosig/echo-tts"}
    assert (
        web_host.owner_token({**space, "ECHO_ZEROGPU_TOKEN": " hf_owner "})
        == "hf_owner"
    )
    assert web_host.owner_token({"ECHO_ZEROGPU_TOKEN": "hf_owner"}) is None
    assert web_host.owner_token({**space, "ECHO_ZEROGPU_TOKEN": "  "}) is None


def test_with_the_owner_token_the_website_server_calls_voices_through_the_public_address(
    tmp_path,
):
    space = {
        "SPACE_ID": "solrosig/echo-tts",
        "ECHO_ZEROGPU_TOKEN": "hf_owner_fixture",
        "ECHO_OLLAMA_TOKEN": "old",
    }
    env = web_host.node_environment(
        ORIGIN, "embedded", 16, tmp_path, space, relay_key="relay-key-fixture"
    )
    assert env["ECHO_TTS_URL"] == ORIGIN + "/api/tts-gpu"
    assert env["ECHO_TTS_TOKEN"] == "hf_owner_fixture"
    assert env["ECHO_TTS_RELAY_KEY"] == "relay-key-fixture"
    assert "ECHO_ZEROGPU_TOKEN" not in env
    assert "ECHO_OLLAMA_TOKEN" not in env
    assert env["ECHO_OLLAMA_URL"] == "http://127.0.0.1:11434"
    assert env["ECHO_OLLAMA_MODEL"] == "llama3.2:3b-t16"
    assert env["PUBLIC_ORIGIN"] == ORIGIN
    assert env["ECHO_DATA_DIR"] == str(tmp_path)


def test_without_the_owner_token_voices_and_the_model_name_stay_as_before(tmp_path):
    plain = web_host.node_environment(
        ORIGIN, "embedded", None, tmp_path, {"SPACE_ID": "solrosig/echo-tts"}
    )
    for name in ("ECHO_TTS_URL", "ECHO_TTS_TOKEN", "ECHO_OLLAMA_MODEL"):
        assert name not in plain
    remote_env = {
        "ECHO_OLLAMA_URL": "https://llm.example",
        "ECHO_OLLAMA_TOKEN": "hf_llm",
    }
    remote = web_host.node_environment(ORIGIN, "remote", 16, tmp_path, remote_env)
    assert remote["ECHO_OLLAMA_URL"] == "https://llm.example"
    assert remote["ECHO_OLLAMA_TOKEN"] == "hf_llm"
    assert "ECHO_OLLAMA_MODEL" not in remote
    unkeyed_env = {
        "SPACE_ID": "solrosig/echo-tts",
        "ECHO_ZEROGPU_TOKEN": "hf_owner_fixture",
    }
    unkeyed = web_host.node_environment(ORIGIN, "embedded", 16, tmp_path, unkeyed_env)
    assert "ECHO_TTS_URL" not in unkeyed and "ECHO_ZEROGPU_TOKEN" not in unkeyed


def gate_with(key):
    seen = []

    async def inner(scope, receive, send):
        seen.append((scope.get("path"), scope.get("raw_path")))
        if scope["type"] == "http":
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": b"ok"})

    return web_host.relay_gate(inner, key), inner, seen


def status_of(gate, path, headers=()):
    sent = []

    async def receive():
        return {"type": "http.request", "body": b""}

    async def send(message):
        sent.append(message)

    scope = {
        "type": "http",
        "path": path,
        "raw_path": path.encode(),
        "headers": list(headers),
    }
    asyncio.run(gate(scope, receive, send))
    return sent[0]["status"]


def test_without_a_relay_key_gradio_is_reached_directly():
    gate, inner, _ = gate_with("")
    assert gate is inner


def test_visitors_voice_requests_go_to_the_website_server_and_only_the_relay_reaches_gradio():
    gate, _, seen = gate_with("relay-key-fixture")
    join = "/api/tts/gradio_api/queue/join"
    assert status_of(gate, join) == 200
    assert seen.pop() == (
        "/_echo_voice_relay" + join,
        ("/_echo_voice_relay" + join).encode(),
    )
    relay = [(b"x-echo-voice-relay", b"relay-key-fixture")]
    assert status_of(gate, "/api/tts-gpu/config", relay) == 200
    assert seen.pop() == ("/api/tts/config", b"/api/tts/config")
    for headers in ([], [(b"x-echo-voice-relay", b"guess")]):
        assert status_of(gate, "/api/tts-gpu/config", headers) == 404
    assert not seen
    assert status_of(gate, "/health") == 200
    assert seen.pop() == ("/health", b"/health")
    asyncio.run(gate({"type": "lifespan"}, None, None))
    assert seen.pop() == (None, None)


def test_the_website_server_receives_relayed_voice_paths_only():
    assert web_host.website_path("/_echo_voice_relay/api/tts/config") == (
        "/api/tts/config",
        True,
    )
    assert web_host.website_path("/_echo_voice_relay/api/study/sessions") is None
    assert web_host.website_path("/api/study/status") == ("/api/study/status", False)
