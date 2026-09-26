"""Build the blinded listening-test site: a static folder a listener can open from a URL.

    python build_test_site.py --out ..\\echo-listening
    python build_test_site.py --out ..\\echo-listening --stimuli 2      # shorter session

Output:
    <out>/index.html  check.html  test.html  done.html      the flow
    <out>/app.css  echo.js                                  vendored, no CDN
    <out>/manifest.json                                     tokens + durations only
    <out>/audio/<token>.wav                                 opaque names
    <out>/.nojekyll                                         or Pages ignores folders starting with _
    research/uat/blind_key_<stamp>.csv                      the key; stays in this repo

The key never enters the site folder: a static host has no server to hide the
token->condition mapping behind, so the only way to hide it is not to ship it. Filenames are
opaque for the same reason: `zipvoice_b4_matched_S01_Q2.wav` in a network tab tells a curious
participant everything the blinding exists to withhold.

Six conditions, two of them expected to fail: four survivors plus two controls at opposite
ends. parlertts should fail on conveyance (quadrant 25.0 %, arousal 50.0 %, four identical
confusion rows) and espeak on naturalness (UTMOS 2.113 against a 3.353 floor). A listener who
rates both well is discriminating on neither axis, a stronger attention check than either
control alone. eSpeak is also the low anchor ITU-R BS.1534 requires, so the scale is
calibrated rather than floating.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import shutil
import wave
from datetime import datetime
from pathlib import Path

QUADRANTS = ("Q1", "Q2", "Q3", "Q4")

#: session -> short label. Order is the reporting order; the browser shuffles the presentation
#: order per participant from a seed derived from the participant code.
CONDITIONS = {
    "2026-08-31_1241_zipvoice_b4_matched": "zipvoice-matched",
    "2026-08-31_2302_chatterbox_x2_matched_v2": "chatterbox-matched",
    "2026-08-09_1911_chatterbox_x2_refs": "chatterbox-refs",
    "2026-07-27_0015_kokoro_check": "kokoro",
    "2026-08-31_2226_parlertts_b4_negative": "parlertts",
    "2026-07-26_2340_espeak_check": "espeak",
}

#: Practice clips come from a session outside the analysed set, so the four trials a listener
#: spends learning the task cannot contaminate a reported cell.
PRACTICE_SESSION = "2026-07-26_1733_sapi_e6_realtest"

PARAM_SET = "rate_volume_pitch"


def token_for(session: str, clip_id: str) -> str:
    """Opaque, stable token for a clip; not reversible without the key.

    Derived from session + clip_id, not assigned randomly, so rebuilds give the same filenames
    (a readable site diff) without keeping state. Opaque so the network tab leaks nothing.
    """
    return hashlib.sha256(f"{session}|{clip_id}".encode()).hexdigest()[:10]


def duration(path: Path) -> float:
    try:
        with wave.open(str(path), "rb") as w:
            return round(w.getnframes() / float(w.getframerate()), 2)
    except Exception:
        return 0.0


def load_register(register: Path) -> "list[dict]":
    return list(csv.DictReader(open(register, encoding="utf-8")))


def select(rows: "list[dict]", stimuli: int) -> "tuple[list[dict], list[dict]]":
    """Balanced selection: every condition x every quadrant x `stimuli` stimuli.

    Stimulus ids are taken in sorted order, not sampled, so the same register and `--stimuli`
    always give the same trials without carrying a seed.
    """
    by = {}
    for r in rows:
        if r.get("param_set") != PARAM_SET:
            continue
        by.setdefault((r.get("session"), r.get("quadrant")), []).append(r)

    trials = []
    for session in CONDITIONS:
        for q in QUADRANTS:
            pool = sorted(by.get((session, q), []), key=lambda r: r.get("stimulus_id", ""))
            for r in pool[:stimuli]:
                trials.append(r)

    practice = []
    for q in QUADRANTS:
        pool = sorted(by.get((PRACTICE_SESSION, q), []), key=lambda r: r.get("stimulus_id", ""))
        if pool:
            practice.append(pool[0])
    return trials, practice


def write_site(out: Path, trials: "list[dict]", practice: "list[dict]", site_src: Path) -> Path:
    (out / "audio").mkdir(parents=True, exist_ok=True)
    manifest = {"version": 1, "test": [], "practice": []}
    key_rows = []

    for kind, group in (("practice", practice), ("test", trials)):
        for r in group:
            src = Path(str(r["audio_path"]).replace("\\", "/"))
            tok = token_for(r["session"], r["clip_id"])
            shutil.copyfile(src, out / "audio" / f"{tok}.wav")
            manifest[kind].append({"token": tok, "seconds": duration(src)})
            key_rows.append({
                "token": tok, "kind": kind, "condition": CONDITIONS.get(r["session"], "practice"),
                "session": r["session"], "engine": r["engine"], "quadrant": r["quadrant"],
                "stimulus_id": r["stimulus_id"], "clip_id": r["clip_id"],
                "audio_path": r["audio_path"],
            })

    (out / "manifest.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    (out / ".nojekyll").write_text("", encoding="utf-8")
    for name in ("index.html", "check.html", "test.html", "done.html", "app.css", "echo.js"):
        shutil.copyfile(site_src / name, out / name)

    key_dir = Path("research/uat")
    key_dir.mkdir(parents=True, exist_ok=True)
    key_path = key_dir / f"blind_key_{datetime.now().strftime('%Y%m%d-%H%M%S')}.csv"
    with open(key_path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(key_rows[0].keys()))
        w.writeheader()
        w.writerows(key_rows)
    return key_path


def main(argv: "list[str] | None" = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--register", default="research/register.csv")
    ap.add_argument("--site-src", default="site")
    ap.add_argument("--out", required=True, help="the site folder (a separate PUBLIC repo)")
    ap.add_argument("--stimuli", type=int, default=3, help="stimuli per condition x quadrant")
    args = ap.parse_args(argv)

    reg = Path(args.register)
    if not reg.exists():
        print(f"Register not found: {reg} — run build_register.py --build first.")
        return 1

    rows = load_register(reg)
    trials, practice = select(rows, args.stimuli)
    if not trials:
        print("No trials selected — check CONDITIONS against the session names in the register.")
        return 1

    out = Path(args.out)
    key = write_site(out, trials, practice, Path(args.site_src))

    mins = sum(t["seconds"] for t in json.loads((out / "manifest.json").read_text())["test"]) / 60
    print(f"Site: {out}")
    print(f"  {len(trials)} test trials + {len(practice)} practice, "
          f"{len(CONDITIONS)} conditions x 4 quadrants x {args.stimuli} stimuli")
    print(f"  audio {mins:.1f} min; allow roughly {len(trials) * 25 / 60:.0f} min per session")
    print(f"  KEY (never copy into the site): {key}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
