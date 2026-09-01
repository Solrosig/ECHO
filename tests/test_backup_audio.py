"""The corpus is the one artefact that cannot be regenerated, so its manifest must be honest.

Two properties carry that: **every** clip is walked (not only registered ones, because 410 of
823 predate `register.csv`), and a manifest is never overwritten.
"""

import csv
import wave
from pathlib import Path

import backup_audio as ba


def _wav(p: Path, frames: bytes = b"\x00\x01" * 100):
    p.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(p), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(22050)
        w.writeframes(frames)


def test_scan_includes_clips_that_no_register_covers(tmp_path):
    root = tmp_path / "sessions"
    _wav(root / "s_old" / "audio" / "eng" / "ps" / "S01_Q1.wav")
    _wav(root / "s_new" / "audio" / "eng" / "ps" / "S01_Q1.wav", b"\x02\x03" * 100)
    digest = ba.sha256_file(root / "s_new" / "audio" / "eng" / "ps" / "S01_Q1.wav")
    with open(root / "s_new" / "register.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["clip_id", "sha256"])
        w.writerow(["c1", digest])

    rows = ba.scan(root)
    assert len(rows) == 2, "a clip with no register must still be manifested"
    by_session = {r["session"]: r for r in rows}
    assert by_session["s_new"]["in_register"] == "yes"
    assert by_session["s_old"]["in_register"] == "no"


def test_manifest_is_timestamped_and_never_overwrites(tmp_path):
    root = tmp_path / "sessions"
    _wav(root / "s" / "audio" / "e" / "p" / "a.wav")
    out = tmp_path / "research"
    first = ba.write_manifest(ba.scan(root), out)
    second = ba.write_manifest(ba.scan(root), out)
    assert first.exists() and second.exists()
    assert len(list(out.glob("audio_manifest_*.csv"))) >= 1


def test_verify_reports_missing_and_corrupt(tmp_path, capsys):
    root = tmp_path / "sessions"
    _wav(root / "s" / "audio" / "e" / "p" / "a.wav")
    _wav(root / "s" / "audio" / "e" / "p" / "b.wav", b"\x04\x05" * 100)
    manifest = ba.write_manifest(ba.scan(root), tmp_path / "research")

    backup = tmp_path / "backup"
    _wav(backup / "s" / "audio" / "e" / "p" / "a.wav", b"\xff\xfe" * 100)   # corrupt
    assert ba.verify(manifest, backup) == 1                                 # b.wav missing
    out = capsys.readouterr().out
    assert "MISSING" in out and "HASH MISMATCH" in out
    assert "do not delete the source" in out.lower()
def test_newest_manifest_removes_the_timestamp_from_the_command_line(tmp_path):
    """A step containing `<stamp>` is a step the operator has to interpret, so resolve it here."""
    assert ba.newest_manifest(tmp_path) is None
    (tmp_path / "audio_manifest_20260101-000000.csv").write_text("x", encoding="utf-8")
    (tmp_path / "audio_manifest_20260901-235959.csv").write_text("x", encoding="utf-8")
    assert ba.newest_manifest(tmp_path).name == "audio_manifest_20260901-235959.csv"


def test_copy_to_resumes_instead_of_restarting(tmp_path):
    """An interrupted 219 MB copy must not start over; identical clips are skipped."""
    root = tmp_path / "sessions"
    _wav(root / "s" / "audio" / "e" / "p" / "a.wav")
    _wav(root / "s" / "audio" / "e" / "p" / "b.wav", b"\x06\x07" * 100)
    rows = ba.scan(root)
    dest = tmp_path / "bk"

    assert ba.copy_to(rows, root, dest) == (2, 0)
    assert ba.copy_to(rows, root, dest) == (0, 2)

    (dest / "s" / "audio" / "e" / "p" / "a.wav").write_bytes(b"corrupted")
    assert ba.copy_to(rows, root, dest) == (1, 1), "a corrupt clip is re-copied, not skipped"
    assert ba.verify(ba.write_manifest(rows, tmp_path / "m"), dest) == 0
