"""The Hugging Face store keeps conversation-reply metrics as immutable pieces that survive restarts."""

import importlib.util
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "persistent_store", ROOT / "standalone" / "deployment" / "huggingface" / "persistent_store.py"
)
persistent_store = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(persistent_store)
Store = persistent_store.Store
METRICS = persistent_store.METRICS


def make_database(local: Path) -> None:
    connection = sqlite3.connect(local / "study.sqlite")
    connection.execute("CREATE TABLE interactive_audio (object_key TEXT, sha256 TEXT)")
    connection.commit()
    connection.close()


def test_only_new_complete_lines_are_kept(tmp_path):
    local, durable = tmp_path / "local", tmp_path / "durable"
    store = Store(local, durable)
    assert store.checkpoint_metrics() is None
    (local / METRICS).write_bytes(b'{"ok":true}\n{"ok":false}\n{"partial"')
    first = store.checkpoint_metrics()
    assert (durable / "metrics" / first).read_bytes() == b'{"ok":true}\n{"ok":false}\n'
    assert store.checkpoint_metrics() is None
    with open(local / METRICS, "ab") as handle:
        handle.write(b":1}\n")
    second = store.checkpoint_metrics()
    assert (durable / "metrics" / second).read_bytes() == b'{"partial":1}\n'
    assert [piece.name for piece in store.metric_pieces()] == sorted([first, second])


def test_a_restart_rebuilds_the_file_and_never_duplicates_lines(tmp_path):
    local, durable = tmp_path / "local", tmp_path / "durable"
    store = Store(local, durable)
    (local / METRICS).write_bytes(b"one\ntwo\n")
    store.checkpoint_metrics()

    # After a restart the Space's temporary disk is empty.
    fresh = tmp_path / "after-restart"
    restarted = Store(fresh, durable)
    assert restarted.restore_metrics() is True
    assert (fresh / METRICS).read_bytes() == b"one\ntwo\n"
    with open(fresh / METRICS, "ab") as handle:
        handle.write(b"three\n")
    piece = restarted.checkpoint_metrics()
    assert (durable / "metrics" / piece).read_bytes() == b"three\n"

    # A web host restarted inside the same container finds the file still there.
    continued = Store(fresh, durable)
    assert continued.restore_metrics() is False
    assert continued.checkpoint_metrics() is None
    assert b"".join(p.read_bytes() for p in continued.metric_pieces()) == b"one\ntwo\nthree\n"


def test_a_study_checkpoint_also_keeps_the_metrics(tmp_path):
    local, durable = tmp_path / "local", tmp_path / "durable"
    local.mkdir()
    make_database(local)
    store = Store(local, durable)
    (local / METRICS).write_bytes(b'{"ok":true}\n')
    manifest = store.checkpoint()
    assert (durable / "snapshots" / manifest["database"]).exists()
    assert b"".join(p.read_bytes() for p in store.metric_pieces()) == b'{"ok":true}\n'


def test_a_metrics_failure_does_not_fail_the_study_checkpoint(tmp_path, monkeypatch, capsys):
    local, durable = tmp_path / "local", tmp_path / "durable"
    local.mkdir()
    make_database(local)
    store = Store(local, durable)

    def broken():
        raise OSError("bucket unavailable")

    monkeypatch.setattr(store, "checkpoint_metrics", broken)
    assert store.checkpoint()["database"].endswith(".sqlite")
    assert "Could not keep conversation-reply metrics" in capsys.readouterr().out
