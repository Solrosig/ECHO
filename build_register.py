"""Register maintenance across the audio corpus.

  python build_register.py --verify
      Check every clip in every research/sessions/*/register.csv: file exists + SHA-256 matches.

  python build_register.py --build [--ingest-db echo.db]
      Consolidate every session register into one master research/register.csv (dedup by
      clip_id), optionally folding in full-system (LLM) turns from the provenance DB.

The controlled corpus is written by synth_stimuli.py (one register.csv per session);
this tool keeps them honest (integrity) and builds a single master register for analysis.
"""

from __future__ import annotations

import argparse
import contextlib
import csv
import hashlib
import sqlite3
import wave
from pathlib import Path

from synth_stimuli import REGISTER_FIELDS as SESSION_FIELDS

MASTER_FIELDS = ["source", "session"] + SESSION_FIELDS


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
            p = Path(r["audio_path"])
            if not p.exists():
                missing += 1
                print("MISSING      ", r["clip_id"], p)
            elif sha256_file(p) != r["sha256"]:
                bad += 1
                print("HASH MISMATCH", r["clip_id"], p)
    print(f"Verified {total} clips across {len(regs)} session(s): {missing} missing, {bad} hash mismatch(es).")
    return 1 if (missing or bad) else 0


def _write_master(out: Path, rows: dict) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=MASTER_FIELDS)
        w.writeheader()
        for cid in sorted(rows):
            w.writerow(rows[cid])


def build(root: str, out: str, db: str | None = None) -> int:
    rows: dict[str, dict] = {}
    for reg in session_registers(root):
        session = reg.parent.name
        for r in csv.DictReader(open(reg, encoding="utf-8")):
            row = {"source": "controlled", "session": session}
            row.update({k: r.get(k, "") for k in SESSION_FIELDS})
            rows[r["clip_id"]] = row
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
