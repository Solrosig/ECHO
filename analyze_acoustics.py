"""Objective acoustic analysis of the synthesized clips (Story E4).

Measures, per clip, the three quantities the voice dials are supposed to move:
    * mean F0    (fundamental frequency, Hz)      <- the PITCH dial
    * loudness   (RMS, dBFS)                       <- the VOLUME dial
    * speaking rate (words per second; text is fixed) <- the RATE dial

This is the OBJECTIVE Before/After that complements listening: it shows, in numbers,
that each dial renders monotonically with its target emotional axis and that the four
quadrants separate -- without relying on anyone's ears.

    python analyze_acoustics.py --register research/register.csv
        -> writes research/acoustics.csv  (every register row + f0_hz, rms_dbfs, words_per_s)
        -> prints a per (param_set x quadrant) summary
        -> prints a neutral -> full "Before/After" table per quadrant

Measurement is intentionally light (numpy only): autocorrelation F0, RMS loudness. It is
meant for RELATIVE comparison across conditions, not absolute phonetic precision.

Method basis (literature):
  * Feature choice — F0 (pitch), loudness (intensity), and rate are the standard minimal
    prosodic descriptors for affective voice analysis, per the Geneva Minimalistic Acoustic
    Parameter Set (GeMAPS; Eyben, Scherer, Schuller et al., 2016, IEEE T-AFFC) and the SER
    feature surveys (El Ayadi, Kamel & Karray, 2011; Scherer, 2003). GeMAPS also standardises
    voice-quality descriptors (jitter, shimmer, HNR) — the valence-relevant channel this tool
    does NOT yet compute (see the extension note in the project log).
  * F0 method — short-time AUTOCORRELATION in the lag domain, i.e. the algorithm of Boersma
    (1993) as used by Praat; robust to noise/jitter and standard for speaking-voice F0.
  * Loudness — RMS energy (dBFS), the intensity correlate used across the SER literature.
  * Rate — words per second (text is fixed). This is a lightweight proxy for the rigorous
    syllable-nuclei speech-rate method of de Jong & Wempe (2009); a later story can adopt it.
Full citations with open-access URLs are recorded in PROJECT_LOG.md (Story E4, measurement basis).
"""

from __future__ import annotations

import argparse
import contextlib
import csv
import math
import wave
from collections import defaultdict
from pathlib import Path
from statistics import mean

import numpy as np

F0_MIN, F0_MAX = 75.0, 400.0     # plausible speaking-voice F0 band (Hz)
SILENCE_DBFS = -60.0             # below this a clip is treated as silent (e.g. the mock engine)


def read_wav(path: Path) -> tuple[np.ndarray, int]:
    """Read a WAV into a mono float array in [-1, 1] plus its sample rate."""
    with contextlib.closing(wave.open(str(path), "rb")) as w:
        n, sr, ch, sw = w.getnframes(), w.getframerate(), w.getnchannels(), w.getsampwidth()
        raw = w.readframes(n)
    if sw == 1:                                   # 8-bit PCM is unsigned
        x = (np.frombuffer(raw, dtype=np.uint8).astype(np.float32) - 128.0) / 128.0
    elif sw == 4:
        x = np.frombuffer(raw, dtype=np.int32).astype(np.float32) / 2147483648.0
    else:                                         # default/most common: 16-bit
        x = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    if ch > 1:
        x = x[::ch]                               # take the first channel
    return x, sr


def rms_dbfs(x: np.ndarray) -> float:
    """Loudness as RMS in dB relative to full scale (0 dBFS = 1.0 amplitude)."""
    if x.size == 0:
        return -120.0
    r = float(np.sqrt(np.mean(x * x)))
    return 20.0 * math.log10(r) if r > 1e-9 else -120.0


def _voiced_f0s(x: np.ndarray, sr: int, fmin: float = F0_MIN, fmax: float = F0_MAX) -> list[float]:
    """Per-voiced-frame F0 estimates via short-time autocorrelation (Boersma-style)."""
    if x.size == 0 or sr <= 0:
        return []
    frame, hop = int(0.04 * sr), int(0.01 * sr)
    min_lag, max_lag = max(1, int(sr / fmax)), int(sr / fmin)
    if frame < 2 or max_lag <= min_lag or x.size < frame:
        return []
    starts = range(0, x.size - frame, hop)
    energies = [float(np.sum(x[s:s + frame] ** 2)) for s in starts]
    if not energies:
        return []
    thr = 0.2 * max(energies)                     # only analyse frames with enough energy
    f0s: list[float] = []
    for s, e in zip(starts, energies):
        if e < thr or e <= 0:
            continue
        fr = x[s:s + frame] - float(np.mean(x[s:s + frame]))
        ac = np.correlate(fr, fr, mode="full")[fr.size - 1:]
        if ac[0] <= 0:
            continue
        seg = ac[min_lag:max_lag + 1]
        if seg.size == 0:
            continue
        lag = min_lag + int(np.argmax(seg))
        if ac[lag] < 0.3 * ac[0]:                 # weak periodicity -> treat as unvoiced
            continue
        f0s.append(sr / lag)
    return f0s


def mean_f0(x: np.ndarray, sr: int, fmin: float = F0_MIN, fmax: float = F0_MAX) -> float:
    """Median F0 over voiced frames. 0.0 if unvoiced/silent."""
    f0s = _voiced_f0s(x, sr, fmin, fmax)
    return round(float(np.median(f0s)), 1) if f0s else 0.0


def f0_stats(x: np.ndarray, sr: int, fmin: float = F0_MIN, fmax: float = F0_MAX) -> dict:
    """F0 level AND variability: median (level), standard deviation and range (spread).
    Arousal raises not only F0 level but its variability, so spread is reported too."""
    f0s = _voiced_f0s(x, sr, fmin, fmax)
    if not f0s:
        return {"f0_hz": 0.0, "f0_sd_hz": 0.0, "f0_range_hz": 0.0}
    arr = np.asarray(f0s, dtype=float)
    return {
        "f0_hz": round(float(np.median(arr)), 1),
        "f0_sd_hz": round(float(np.std(arr)), 1),
        "f0_range_hz": round(float(arr.max() - arr.min()), 1),
    }


def analyze_clip(path: Path, text: str = "") -> dict:
    """Measure one clip: F0 (Hz), loudness (dBFS), speaking rate (words/s), duration (s)."""
    x, sr = read_wav(path)
    dur = x.size / sr if sr else 0.0
    loud = round(rms_dbfs(x), 1)
    st = f0_stats(x, sr)
    return {
        "f0_hz": st["f0_hz"],
        "f0_sd_hz": st["f0_sd_hz"],
        "f0_range_hz": st["f0_range_hz"],
        "rms_dbfs": loud,
        "words_per_s": round(len(text.split()) / dur, 2) if dur > 0 and text else 0.0,
        "measured_dur_s": round(dur, 3),
        "silent": "yes" if loud <= SILENCE_DBFS else "no",
    }


MEASURED_COLS = ["f0_hz", "f0_sd_hz", "f0_range_hz", "rms_dbfs", "words_per_s", "measured_dur_s", "silent"]


def _fmt(v) -> str:
    return f"{v:6.1f}" if isinstance(v, float) else f"{str(v):>6}"


def _summary(rows: list[dict]) -> None:
    """Mean F0 / rate / loudness per (param_set, quadrant), audible clips only."""
    audible = [r for r in rows if r["silent"] == "no"]
    if not audible:
        print("  (no audible clips to summarise -- run this on a REAL engine session, not mock)")
        return
    groups: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for r in audible:
        groups[(r.get("param_set", "?"), r.get("quadrant", "?"))].append(r)
    print("\n== Mean acoustics per param_set x quadrant (audible clips) ==")
    print(f"  {'param_set':<20}{'quad':<6}{'F0 Hz':>8}{'words/s':>9}{'RMS dBFS':>10}{'n':>4}")
    for (ps, q) in sorted(groups):
        g = groups[(ps, q)]
        f0 = mean([r['f0_hz'] for r in g if r['f0_hz'] > 0] or [0.0])
        wps = mean([r['words_per_s'] for r in g])
        db = mean([r['rms_dbfs'] for r in g])
        print(f"  {ps:<20}{q:<6}{f0:8.1f}{wps:9.2f}{db:10.1f}{len(g):4d}")


def _before_after(rows: list[dict], before: str = "neutral", after: str = "rate_volume_pitch") -> None:
    """Objective Before/After: neutral baseline vs full emotion, per quadrant."""
    audible = [r for r in rows if r["silent"] == "no"]
    def cell(ps: str, q: str, key: str) -> float | None:
        vals = [r[key] for r in audible if r.get("param_set") == ps and r.get("quadrant") == q
                and (key != "f0_hz" or r[key] > 0)]
        return round(mean(vals), 1) if vals else None
    quads = sorted({r.get("quadrant", "?") for r in audible})
    have = {r.get("param_set") for r in audible}
    if before not in have or after not in have:
        print(f"\n== Before/After skipped: need both '{before}' and '{after}' param-sets "
              f"(present: {sorted(have)}). Run synth with --param-set all. ==")
        return
    print(f"\n== Before/After  ({before}  ->  {after})  per quadrant ==")
    print(f"  {'quad':<6}{'F0 Δ Hz':>18}{'rate Δ w/s':>16}{'loud Δ dB':>16}")
    for q in quads:
        line = f"  {q:<6}"
        for key, w in (("f0_hz", 18), ("words_per_s", 16), ("rms_dbfs", 16)):
            b, a = cell(before, q, key), cell(after, q, key)
            txt = f"{b}->{a} ({a - b:+.1f})" if (b is not None and a is not None) else "n/a"
            line += f"{txt:>{w}}"
        print(line)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--register", default="research/register.csv",
                    help="register CSV to analyse (master or a session register.csv)")
    ap.add_argument("--out", default="research/acoustics.csv")
    ap.add_argument("--before", default="neutral")
    ap.add_argument("--after", default="rate_volume_pitch")
    args = ap.parse_args(argv)

    src = Path(args.register)
    if not src.exists():
        print(f"Register not found: {src}. Build one first (build_register.py --build).")
        return 1

    measured, missing = [], 0
    for r in csv.DictReader(open(src, encoding="utf-8")):
        p = Path(r.get("audio_path", ""))
        if not p.exists():
            missing += 1
            continue
        row = dict(r)
        row.update(analyze_clip(p, r.get("text", "")))
        measured.append(row)

    if not measured:
        print(f"No clips found on disk from {src} ({missing} missing paths).")
        return 1

    fields = list(dict.fromkeys(list(measured[0].keys())))
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(measured)

    n_sil = sum(1 for r in measured if r["silent"] == "yes")
    print(f"Analysed {len(measured)} clips ({n_sil} silent, {missing} missing) -> {out}")
    _summary(measured)
    _before_after(measured, args.before, args.after)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
