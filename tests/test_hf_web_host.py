"""The Space's embedded model gets one thread per CPU its container may use, not one per core of the host."""

import importlib.util
import sys
from pathlib import Path

import pytest

HF = Path(__file__).resolve().parents[1] / "standalone" / "deployment" / "huggingface"
sys.path.insert(0, str(HF))
_spec = importlib.util.spec_from_file_location("web_host", HF / "web_host.py")
web_host = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(web_host)


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


def test_llama_server_receives_the_thread_count_through_ollama(tmp_path, monkeypatch):
    monkeypatch.delenv("LLAMA_ARG_THREADS", raising=False)
    env = web_host.ollama_environment(tmp_path, 2)
    assert env["LLAMA_ARG_THREADS"] == "2"
    assert env["OLLAMA_MODELS"] == str(tmp_path / "models")
    assert "LLAMA_ARG_THREADS" not in web_host.ollama_environment(tmp_path, None)
