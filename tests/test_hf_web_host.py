"""The Space's hosting helpers: model threads within the container's CPU limit, and server voices on the owner's quota."""

import asyncio
import importlib.util
import sys
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
