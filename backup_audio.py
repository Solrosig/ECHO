"""Audio backup manifest and verification — the corpus is the one thing that cannot be rebuilt.

    python backup_audio.py --manifest
        Hash EVERY .wav under research/sessions (registered or not) into a timestamped
        research/audio_manifest_<stamp>.csv. Never overwrites.

    python backup_audio.py --copy-to D:/ECHO_AUDIO_BACKUP
        Manifest, copy every clip there, and verify - one command, no timestamp to type.
        Re-running resumes: clips already present with a matching hash are skipped.

    python backup_audio.py --verify D:/ECHO_AUDIO_BACKUP
        Re-check an existing backup against the newest manifest.

**Why this is separate from `build_register.py --verify`.** That tool verifies clips that are
IN a register, which is the right check for the analysed corpus. But `synth_stimuli.py` only
began writing `register.csv` on 2026-07-26, and **410 of the 823 clips predate it** — seven
session folders with audio and no register at all. Those clips are invisible to every integrity
check the project has, so a silent corruption or a partial copy would go unnoticed precisely in
the oldest and least reproducible part of the corpus. This tool walks the filesystem instead of
the registers, so nothing is invisible to it.

The scorecard can be rebuilt from the audio. The audio cannot be rebuilt from anything: the
stochastic engines are seeded, but the reference clips, the model checkpoints and the engine
versions that produced them are not all pinned, and two of the six engines are out-of-process
installs that no longer match their original environments.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import shutil
from datetime import datetime
from pathlib import Path

FIELDS = ["session", "rel_path", "bytes", "sha256", "in_register"]


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def registered_hashes(sessions_root: Path) -> set:
    """Every SHA-256 that appears in some session register — used only to mark coverage."""
    seen = set()
    for reg in sorted(sessions_root.glob("*/register.csv")):
        try:
            for r in csv.DictReader(open(reg, encoding="utf-8")):
                if r.get("sha256"):
                    seen.add(r["sha256"])
        except Exception:
            continue
    return seen


def scan(sessions_root: Path) -> "list[dict]":
    known = registered_hashes(sessions_root)
    rows = []
    for wav in sorted(sessions_root.glob("*/audio/**/*.wav")):
        digest = sha256_file(wav)
        rows.append({
            "session": wav.relative_to(sessions_root).parts[0],
            "rel_path": wav.relative_to(sessions_root).as_posix(),
            "bytes": wav.stat().st_size,
            "sha256": digest,
            "in_register": "yes" if digest in known else "no",
        })
    return rows


def write_manifest(rows: "list[dict]", out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"audio_manifest_{datetime.now().strftime('%Y%m%d-%H%M%S')}.csv"
    with open(out, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)
    return out


def newest_manifest(out_dir: Path) -> "Path | None":
    """The most recent manifest in `out_dir`, so no command line has to carry a timestamp.

    Manifests are timestamped and never overwritten, which is right for a record but makes
    every filename unguessable. A step that reads `--manifest-file research/audio_manifest_
    <stamp>.csv` is a step the operator has to interpret, and an interpreted step is a step
    that gets typed wrong. The newest manifest is always the one that matches the current
    corpus, so resolving it here removes the placeholder entirely.
    """
    files = sorted(Path(out_dir).glob("audio_manifest_*.csv"))
    return files[-1] if files else None


def copy_to(rows: "list[dict]", sessions_root: Path, dest: Path) -> "tuple[int, int]":
    """Copy every manifested clip to `dest`, preserving the session/audio tree. Returns
    (copied, skipped_identical).

    Files already present with a matching SHA-256 are skipped, so re-running after an
    interrupted copy resumes instead of starting over, and an unchanged corpus costs nothing.
    """
    copied = skipped = 0
    for r in rows:
        src = sessions_root / r["rel_path"]
        dst = dest / r["rel_path"]
        if dst.exists() and dst.stat().st_size == int(r["bytes"]) and sha256_file(dst) == r["sha256"]:
            skipped += 1
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        copied += 1
    return copied, skipped


def verify(manifest: Path, backup_root: Path) -> int:
    rows = list(csv.DictReader(open(manifest, encoding="utf-8")))
    missing = bad = 0
    for r in rows:
        p = backup_root / r["rel_path"]
        if not p.exists():
            missing += 1
            print("MISSING      ", r["rel_path"])
        elif sha256_file(p) != r["sha256"]:
            bad += 1
            print("HASH MISMATCH", r["rel_path"])
    total_mb = sum(int(r["bytes"]) for r in rows) / 1048576
    print(f"\nChecked {len(rows)} clips ({total_mb:.1f} MB) against {manifest.name}: "
          f"{missing} missing, {bad} corrupt.")
    if missing or bad:
        print("BACKUP INCOMPLETE — do not delete the source.")
        return 1
    print("BACKUP VERIFIED — every clip present and byte-identical.")
    return 0


def main(argv: "list[str] | None" = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--sessions-root", default="research/sessions")
    ap.add_argument("--out-dir", default="research")
    ap.add_argument("--manifest", action="store_true", help="hash every clip and write a manifest")
    ap.add_argument("--verify", metavar="BACKUP_ROOT", default=None,
                    help="verify a backup copy (uses the newest manifest unless --manifest-file)")
    ap.add_argument("--copy-to", metavar="BACKUP_ROOT", default=None,
                    help="write a manifest, copy every clip there, then verify - one command")
    ap.add_argument("--manifest-file", default=None)
    args = ap.parse_args(argv)

    root = Path(args.sessions_root)
    if args.copy_to:
        rows = scan(root)
        out = write_manifest(rows, Path(args.out_dir))
        total_mb = sum(r["bytes"] for r in rows) / 1048576
        print(f"Manifest: {out}  ({len(rows)} clips, {total_mb:.1f} MB)")
        dest = Path(args.copy_to)
        copied, skipped = copy_to(rows, root, dest)
        print(f"Copied {copied}, already identical {skipped}  ->  {dest}")
        return verify(out, dest)
    if args.manifest:
        rows = scan(root)
        out = write_manifest(rows, Path(args.out_dir))
        unregistered = sum(1 for r in rows if r["in_register"] == "no")
        unique = len({r["sha256"] for r in rows})
        total_mb = sum(r["bytes"] for r in rows) / 1048576
        print(f"Manifest: {out}  ({len(rows)} files, {total_mb:.1f} MB)")
        print(f"  {len(rows) - unregistered} covered by a session register, "
              f"{unregistered} NOT — no hash for those exists anywhere else.")
        print(f"  {unique} unique waveforms ({len(rows) - unique} byte-identical duplicates) "
              f"— the file count is not the count of distinct audio.")
        return 0
    if args.verify:
        manifest = Path(args.manifest_file) if args.manifest_file else newest_manifest(Path(args.out_dir))
        if manifest is None:
            print("No manifest found. Run --manifest first.")
            return 1
        print(f"Using manifest: {manifest}")
        return verify(manifest, Path(args.verify))
    ap.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
