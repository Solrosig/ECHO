"""Register maintenance across the audio corpus.

  python build_register.py --verify
      Check every clip in every research/sessions/*/register.csv: file exists + SHA-256 matches.

  python build_register.py --build [--ingest-db echo.db]
      Consolidate every session register into one master research/register.csv (dedup by
      SESSION + clip_id), optionally folding in full-system (LLM) turns from the provenance DB.
      The previous master is ARCHIVED as register_superseded-<stamp>.csv before rewriting —
      the index keeps its canonical name so downstream tools still find it, and no version
      of it is ever lost.

The controlled corpus is written by synth_stimuli.py (one register.csv per session);
this tool keeps them honest (integrity) and builds a single master register for analysis.
"""

from __future__ import annotations

import argparse
import contextlib
import csv
import hashlib
import shutil
import sqlite3
import wave
from datetime import datetime
from pathlib import Path

from synth_stimuli import REGISTER_FIELDS as SESSION_FIELDS

MASTER_FIELDS = ["source", "session"] + SESSION_FIELDS


def resolve_audio_path(raw: str) -> Path:
    """Resolve an `audio_path` from a register in a CROSS-PLATFORM way.

    Registers written on Windows store backslash paths (`research\\sessions\\...`), which are
    not path separators on Linux/macOS — so a corpus produced on one OS appeared 100 % 'missing'
    on another (discovered by the M4 integrity check). Normalising separators here makes the
    stored corpus portable without rewriting existing registers, which the reproducibility
    package (C2) requires.
    """
    return Path(str(raw).replace("\\", "/"))


def sha256_file(p: Path) -> str:
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def wav_duration(p: Path):
    try:
        with contextlib.closing(wave.open(str(p), "rb")) as w:
            return round(w.getnframes() / float(w.getframerate()), 3)
    except Exception:
        return ""


def session_registers(root: str) -> list[Path]:
    return sorted(Path(root).glob("*/register.csv"))


def verify(root: str) -> int:
    regs = session_registers(root)
    total = missing = bad = 0
    for reg in regs:
        for r in csv.DictReader(open(reg, encoding="utf-8")):
            total += 1
            p = resolve_audio_path(r["audio_path"])
            if not p.exists():
                missing += 1
                print("MISSING      ", r["clip_id"], p)
            elif sha256_file(p) != r["sha256"]:
                bad += 1
                print("HASH MISMATCH", r["clip_id"], p)
    print(f"Verified {total} clips across {len(regs)} session(s): {missing} missing, {bad} hash mismatch(es).")
    return 1 if (missing or bad) else 0


def _archive_existing(out: Path) -> "Path | None":
    """Move an existing master register aside before rewriting it. Returns the archive path.

    **Why an archive rather than a timestamped output.** The other result writers
    (`naturalness.py`, `emotion_conveyance.py`) never overwrite: they write to a timestamped
    sibling and leave the original alone. That is right for a *result* — each run is its own
    finding and both are kept.

    The master register is not a result; it is an **index**, and downstream tools default to
    its canonical path. Writing a timestamped index would leave every consumer reading a
    stale file, so the non-overwrite rule is honoured the other way round: **the previous
    index is archived, and the canonical name is rewritten.** Nothing is lost, and
    `research/register.csv` still means "the current index".

    This was added on 2026-08-31 after the function was found to call `open(out, "w")`
    unconditionally. It had been rewriting a 300-row register with no copy taken — recoverable
    only because the session folders it is derived from still existed, which is luck rather
    than design.
    """
    if not out.exists():
        return None
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    archive = out.with_name(f"{out.stem}_superseded-{stamp}{out.suffix}")
    i = 1
    while archive.exists():
        archive = out.with_name(f"{out.stem}_superseded-{stamp}-{i}{out.suffix}")
        i += 1
    shutil.copy2(out, archive)
    return archive


def _write_master(out: Path, rows: dict) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    archive = _archive_existing(out)
    if archive:
        print(f"  previous index archived -> {archive}")
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=MASTER_FIELDS)
        w.writeheader()
        for cid in sorted(rows):
            w.writerow(rows[cid])


def build(root: str, out: str, db: str | None = None) -> int:
    rows: dict[tuple, dict] = {}
    for reg in session_registers(root):
        session = reg.parent.name
        for r in csv.DictReader(open(reg, encoding="utf-8")):
            row = {"source": "controlled", "session": session}
            row.update({k: r.get(k, "") for k in SESSION_FIELDS})
            # Dedup key includes the SESSION. clip_id is sha256(engine|param_set|stimulus|quadrant),
            # so two renders of the same design — e.g. an A/B experiment where only an engine
            # SETTING differs (Chatterbox condition A: arousal only, vs B: + reference style) —
            # collide on clip_id and the later session would silently overwrite the earlier one,
            # destroying the comparison at consolidation. Sessions are immutable and uniquely
            # named, so keying on (session, clip_id) preserves every rendered clip while still
            # removing genuine duplicates within a session.
            rows[(session, r["clip_id"])] = row
    n_ctrl = len(rows)

    if db:
        conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        for r in conn.execute("SELECT * FROM turns"):
            keys = r.keys()
            cid = hashlib.sha256(r["turn_uuid"].encode()).hexdigest()[:10]
            p = Path(r["audio_path"])
            row = {k: "" for k in MASTER_FIELDS}
            row.update({
                "source": "full-system", "session": "", "clip_id": cid,
                "blind_id": "B" + hashlib.sha256(cid.encode()).hexdigest()[:6],
                "created": r["ts"], "engine": r["engine"], "param_set": "system-default",
                "quadrant": r["quadrant"], "valence": r["valence"], "arousal": r["arousal"],
                "intensity": r["intensity"], "rate": r["rate"],
                "volume": r["volume"] if "volume" in keys else "",
                "pitch": r["pitch"] if "pitch" in keys else "",
                "model": r["model"], "text": r["reply"], "audio_path": r["audio_path"],
                "sha256": sha256_file(p) if p.exists() else "",
                "duration_s": wav_duration(p) if p.exists() else "",
            })
            rows[cid] = row
        conn.close()

    _write_master(Path(out), rows)
    print(f"Master register: {out}  ({len(rows)} clips: {n_ctrl} controlled + {len(rows) - n_ctrl} full-system)")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--sessions-root", default="research/sessions")
    ap.add_argument("--out", default="research/register.csv")
    ap.add_argument("--verify", action="store_true")
    ap.add_argument("--build", action="store_true")
    ap.add_argument("--ingest-db", default=None)
    args = ap.parse_args(argv)
    if args.verify:
        return verify(args.sessions_root)
    if args.build:
        return build(args.sessions_root, args.out, args.ingest_db)
    ap.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
