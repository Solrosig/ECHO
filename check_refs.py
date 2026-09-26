"""Validate the per-quadrant emotional reference clips used by the native-conditioning engine.

The reference clips (`refs/Q1.wav` .. `refs/Q4.wav`) are the valence channel: Chatterbox imitates
both the speaker and the emotional delivery of the clip it is given. A bad reference silently
degrades every synthesised clip and a render costs ~20 minutes, so check the four files first.

    python check_refs.py                # checks ./refs
    python check_refs.py --dir refs     # explicit

Checks per file: present · readable · mono · sample rate · duration in the usable band ·
peak level (clipping / too quiet) · rough silence share. Prints PASS/WARN/FAIL per clip and a
verdict. Warnings are advisory; FAIL means the clip should be re-recorded.
"""

from __future__ import annotations

import argparse
import contextlib
import wave
from pathlib import Path

QUADRANTS = ("Q1", "Q2", "Q3", "Q4")
LABELS = {"Q1": "happy / excited", "Q2": "upset / agitated",
          "Q3": "sad / subdued", "Q4": "calm / content"}
MIN_S, MAX_S = 3.0, 15.0          # too short -> weak style; too long -> slow + no benefit
MIN_SR = 16000                    # below this the style embedding degrades
PEAK_MAX = 0.99                   # peak at/above this -> advisory only (see CLIP_FAIL)
CLIP_FAIL = 0.001                 # >=0.1% of samples pinned at full scale -> real clipping
PEAK_MIN = 0.10                   # below this a clip is "quiet" (see set-relative logic)
SILENT_MAX = 0.01                 # below this it is effectively silence -> always a failure


def _read(path: Path):
    import numpy as np

    with contextlib.closing(wave.open(str(path), "rb")) as w:
        n, sr, ch, sw = w.getnframes(), w.getframerate(), w.getnchannels(), w.getsampwidth()
        raw = w.readframes(n)
    if sw == 1:
        x = (np.frombuffer(raw, dtype=np.uint8).astype("float32") - 128.0) / 128.0
    elif sw == 4:
        x = np.frombuffer(raw, dtype="<i4").astype("float32") / 2147483648.0
    else:
        x = np.frombuffer(raw, dtype="<i2").astype("float32") / 32768.0
    if ch > 1:
        x = x.reshape(-1, ch).mean(axis=1)      # downmix for measurement only
    return x, sr, ch


def check_clip(path: Path, set_peak: float = 0.0) -> dict:
    """Measure one reference clip and collect problems, warnings and notes.

    `set_peak` is the loudest peak across the whole reference set. Emotional references are
    supposed to have a wide dynamic range: in RAVDESS, 'angry' peaks at 0.82 and 'calm' at
    0.02 (35x), which is the loudness cue for arousal, not a recording fault. An absolute floor
    would reject exactly that property, so a clip that is quiet relative to a loud set counts
    as intentional dynamics. Only near-digital silence, or a uniformly quiet set (a real gain
    problem), is a failure.
    """
    import numpy as np

    out = {"file": path.name, "problems": [], "warnings": []}
    if not path.exists():
        out["problems"].append("missing")
        return out
    try:
        x, sr, ch = _read(path)
    except Exception as exc:
        out["problems"].append(f"unreadable ({exc}); export as WAV signed 16-bit PCM")
        return out

    dur = len(x) / sr if sr else 0.0
    peak = float(np.max(np.abs(x))) if x.size else 0.0
    # Silence share is measured relative to the clip's own peak (~ -34 dB below it). An
    # absolute threshold reports a quiet but clean professional recording as ~99 % "silence";
    # a relative one measures the actual pause structure.
    floor = max(0.02 * peak, 1e-4)
    quiet_share = float(np.mean(np.abs(x) < floor)) if x.size else 1.0
    # Judge clipping by the share of samples pinned at the ceiling, not by peak alone: a few
    # samples at full scale are inaudible and do not measurably affect HNR/jitter, while
    # sustained clipping flattens the waveform and corrupts voice quality.
    clip_share = float(np.mean(np.abs(x) >= 0.995)) if x.size else 0.0
    out.update({"seconds": round(dur, 2), "sr": sr, "channels": ch,
                "peak": round(peak, 3), "silence_share": round(quiet_share, 2),
                "clip_share": clip_share})

    if dur < MIN_S:
        out["problems"].append(f"too short ({dur:.1f}s < {MIN_S}s) — style embedding will be weak")
    elif dur > MAX_S:
        out["warnings"].append(f"longer than {MAX_S}s — no benefit, slower to process")
    if sr < MIN_SR:
        out["problems"].append(f"sample rate {sr} Hz < {MIN_SR} Hz")
    if ch > 1:
        out["warnings"].append(f"{ch} channels — mono is preferred")
    if clip_share >= CLIP_FAIL:
        out["problems"].append(
            f"{clip_share:.2%} of samples clipped — re-record with lower input gain")
    elif peak >= PEAK_MAX:
        out["warnings"].append(
            f"peak {peak:.3f} touches full scale ({clip_share:.3%} of samples) — audibly harmless, "
            "but lower the gain slightly next time")
    # Level: distinguish "silent/broken" from "quiet on purpose" from "whole set under-recorded".
    rel = peak / set_peak if set_peak > 0 else 1.0
    if peak < SILENT_MAX:
        out["problems"].append(f"peak {peak:.3f} — effectively silent; re-record")
    elif peak < PEAK_MIN and rel > 0.5:
        # quiet and close to the loudest clip in the set -> the whole set is under-recorded
        out["problems"].append(f"peak {peak:.2f} — the whole set is too quiet; raise input gain")
    elif peak < PEAK_MIN:
        out["notes"] = out.get("notes", [])
        out["notes"].append(
            f"quiet ({peak:.3f}, {rel:.0%} of the loudest clip) — expected for a low-arousal "
            "emotion; kept as intentional dynamics")
    if quiet_share > 0.75:
        out["warnings"].append(
            f"{quiet_share:.0%} below −34 dB relative to its own peak — trim leading/trailing silence")
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dir", default="refs", help="folder holding Q1.wav .. Q4.wav")
    args = ap.parse_args(argv)
    root = Path(args.dir)

    print(f"Reference clips in '{root}' (the VALENCE channel for the native-emotion engine)\n")
    # First pass: find the set's loudest peak, so quiet low-arousal clips are judged relative
    # to it rather than against an absolute floor (see check_clip).
    peaks = [check_clip(root / f"{q}.wav").get("peak", 0.0) for q in QUADRANTS]
    set_peak = max([p for p in peaks if isinstance(p, float)] or [0.0])

    print(f"  {'clip':<8}{'emotion':<20}{'sec':>6}{'sr':>8}{'ch':>4}{'peak':>7}{'sil':>6}  status")
    failures = 0
    for q in QUADRANTS:
        r = check_clip(root / f"{q}.wav", set_peak=set_peak)
        status = "FAIL" if r["problems"] else ("WARN" if r["warnings"] else "PASS")
        failures += 1 if r["problems"] else 0
        if "seconds" in r:
            print(f"  {q + '.wav':<8}{LABELS[q]:<20}{r['seconds']:>6}{r['sr']:>8}"
                  f"{r['channels']:>4}{r['peak']:>7}{r['silence_share']:>6}  {status}")
        else:
            print(f"  {q + '.wav':<8}{LABELS[q]:<20}{'-':>6}{'-':>8}{'-':>4}{'-':>7}{'-':>6}  {status}")
        for p in r["problems"]:
            print(f"           FAIL: {p}")
        for w in r["warnings"]:
            print(f"           warn: {w}")
        for nte in r.get("notes", []):
            print(f"           note: {nte}")

    if failures:
        print(f"\n{failures} clip(s) need attention — fix before rendering (a render costs ~20 min).")
        return 1
    print("\nAll four references usable. Render condition B with:")
    print("  python synth_stimuli.py --engine chatterbox --param-set rate_volume_pitch "
          "--label chatterbox_x2_refs --purpose \"X2 condition B: + reference style (valence)\"")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
