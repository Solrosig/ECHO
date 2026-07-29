"""Objective naturalness (Story N4): predict a no-reference MOS per clip with UTMOS and
rank the engines (SAPI vs eSpeak vs Kokoro).

UTMOS (Saeki et al., 2022 — VoiceMOS Challenge winner) is a *learned no-reference* MOS
predictor: it estimates the human naturalness rating (1-5) straight from the waveform, with
no reference recording needed. Loaded via SpeechMOS through torch.hub (tarepan/SpeechMOS).
PyTorch/torchaudio/librosa are heavy and live in the OPTIONAL eval layer, so anything that
touches the predictor fails with a clear message where they're absent (core stays light).

    python naturalness.py --register research/register.csv
        -> writes naturalness.csv (register rows + `utmos`) beside the register (never overwrites)
        -> prints mean UTMOS per engine  (the SAPI vs eSpeak vs Kokoro naturalness ranking)

Run on the MASTER register (build_register.py --build over all engine sessions) to compare
engines in one table, or on a single session's register.csv.
"""

from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from statistics import mean

_PREDICTOR = None


def _utmos_predictor():
    """Lazy-load the UTMOS predictor via torch.hub (downloaded on first use, then cached)."""
    global _PREDICTOR
    if _PREDICTOR is None:
        try:
            import torch
            # FIX: torchaudio is imported by UTMOS's OWN model code, not by us — so a missing
            # torchaudio surfaced as a confusing ModuleNotFoundError from deep inside the hub
            # module. Checking it here turns that into an actionable dependency message.
            import torchaudio  # noqa: F401
        except Exception as exc:                 # torch / torchaudio absent
            raise RuntimeError(
                "UTMOS needs PyTorch AND torchaudio — install the eval extras: "
                "`pip install torch torchaudio librosa` (CPU wheels are fine). "
                "torchaudio is required by the UTMOS model itself."
            ) from exc
        try:
            _PREDICTOR = torch.hub.load("tarepan/SpeechMOS:v1.2.0", "utmos22_strong", trust_repo=True)
        except Exception as exc:
            raise RuntimeError(
                "Could not load UTMOS via torch.hub. If your network blocks GitHub/TLS, the hub "
                "cache lives in ~/.cache/torch/hub — the repo zip can be placed there manually. "
                f"Original error: {exc}"
            ) from exc
    return _PREDICTOR


def predict_mos(wav_path) -> float:
    """No-reference UTMOS naturalness score (≈1-5) for one clip."""
    import librosa
    import torch

    wave, sr = librosa.load(str(wav_path), sr=None, mono=True)
    score = _utmos_predictor()(torch.from_numpy(wave).unsqueeze(0), sr)
    return float(score.item() if hasattr(score, "item") else score[0])


def _resolve_out(path: Path, force: bool) -> Path:
    """Never overwrite: timestamped sibling if the target exists (matches the E6.1 rule)."""
    if force or not path.exists():
        return path
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    cand = path.with_name(f"{path.stem}_{stamp}{path.suffix}")
    i = 1
    while cand.exists():
        cand = path.with_name(f"{path.stem}_{stamp}-{i}{path.suffix}")
        i += 1
    return cand


def _summary(rows: list[dict]) -> None:
    groups: dict[str, list[float]] = defaultdict(list)
    for r in rows:
        try:
            groups[r.get("engine", "?")].append(float(r["utmos"]))
        except (KeyError, TypeError, ValueError):
            pass
    if not groups:
        return
    print("\n== Mean UTMOS naturalness per engine (higher = more natural; ~1-5) ==")
    print(f"  {'engine':<12}{'mean UTMOS':>12}{'n':>5}")
    for eng in sorted(groups, key=lambda e: -mean(groups[e])):     # most natural first
        vals = groups[eng]
        print(f"  {eng:<12}{mean(vals):12.3f}{len(vals):5d}")
    _confound_check(rows, groups)


def _confound_check(rows: list[dict], groups: dict) -> None:
    """CONFOUND CHECK (monitoring plan M3): is the naturalness difference driven by the ENGINE
    or by ECHO's own dial settings? Prints mean UTMOS per engine x param_set and compares the
    between-engine spread with the largest within-engine (dial) spread. A large ratio means the
    comparison measures the engine, as intended. A monotonic decline across param-sets is itself
    a finding: the cost in naturalness of adding expressive dials."""
    cells: dict[tuple, list[float]] = defaultdict(list)
    for r in rows:
        try:
            cells[(r.get("engine", "?"), r.get("param_set", "?"))].append(float(r["utmos"]))
        except (KeyError, TypeError, ValueError):
            pass
    psets = [p for p in ("neutral", "rate", "rate_volume", "rate_volume_pitch")
             if any(k[1] == p for k in cells)]
    if len(psets) < 2 or not groups:
        return
    print("\n== Confound check — mean UTMOS per engine x param_set (M3) ==")
    print(f"  {'engine':<12}" + "".join(f"{p[:13]:>15}" for p in psets) + f"{'dial spread':>13}")
    worst = 0.0
    for eng in sorted(groups, key=lambda e: -mean(groups[e])):
        vals = [mean(cells[(eng, p)]) for p in psets if (eng, p) in cells]
        spread = max(vals) - min(vals) if vals else 0.0
        worst = max(worst, spread)
        print(f"  {eng:<12}" + "".join(
            f"{mean(cells[(eng, p)]):15.3f}" if (eng, p) in cells else f"{'-':>15}" for p in psets
        ) + f"{spread:13.3f}")
    eng_means = [mean(v) for v in groups.values()]
    eng_spread = max(eng_means) - min(eng_means)
    ratio = eng_spread / worst if worst > 0 else float("inf")
    verdict = "PASS — engine effect dominates" if ratio >= 3 else "CHECK — dial effect is comparable"
    print(f"  engine spread {eng_spread:.3f}  vs  max dial spread {worst:.3f}   "
          f"(ratio {ratio:.1f}x)  ->  {verdict}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--register", default="research/register.csv",
                    help="register to score (master register or a session register.csv)")
    ap.add_argument("--out", default=None,
                    help="output CSV (default: naturalness.csv beside the register); never overwrites")
    ap.add_argument("--force", action="store_true", help="allow overwriting an existing --out")
    args = ap.parse_args(argv)

    src = Path(args.register)
    if not src.exists():
        print(f"Register not found: {src}. Build one (build_register.py --build) or pass a session register.csv.")
        return 1

    rows = [r for r in csv.DictReader(open(src, encoding="utf-8")) if r.get("silent") != "yes"]
    measured, missing = [], 0
    for r in rows:
        # backslash-normalised: registers written on Windows must still resolve on Linux/macOS
        p = Path(str(r.get("audio_path", "")).replace("\\", "/"))
        if not p.exists():
            missing += 1
            continue
        row = dict(r)
        row["utmos"] = round(predict_mos(p), 3)
        measured.append(row)

    if not measured:
        print(f"No clips found on disk from {src} ({missing} missing paths).")
        return 1

    fields = list(dict.fromkeys(list(measured[0].keys())))
    out = Path(args.out) if args.out else src.parent / "naturalness.csv"
    out = _resolve_out(out, args.force)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(measured)

    print(f"Scored {len(measured)} clips ({missing} missing) -> {out}")
    _summary(measured)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
