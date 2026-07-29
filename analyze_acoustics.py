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

Measurement uses the validated Praat backend (via Parselmouth) for F0 and voice quality
when it is installed, with a numpy autocorrelation fallback; loudness (RMS dBFS) and rate
are always numpy for a consistent scale. It is meant for RELATIVE comparison across
conditions, not absolute phonetic precision.

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
from datetime import datetime
from pathlib import Path
from statistics import mean

import numpy as np

try:                                             # optional: validated Praat backend
    import parselmouth
    from parselmouth.praat import call
    _HAVE_PRAAT = True
except Exception:                                # pragma: no cover
    _HAVE_PRAAT = False

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


def _praat_features(path: Path, fmin: float = F0_MIN, fmax: float = F0_MAX) -> dict:
    """Validated F0 (level + spread) and voice quality (jitter %, shimmer %, HNR dB) via
    Praat (Boersma) through Parselmouth. Undefined values (e.g. unvoiced) become ''."""
    snd = parselmouth.Sound(str(path))
    f0 = snd.to_pitch(pitch_floor=fmin, pitch_ceiling=fmax).selected_array["frequency"]
    voiced = f0[f0 > 0]
    if voiced.size:
        f0_hz = round(float(np.median(voiced)), 1)
        f0_sd = round(float(np.std(voiced)), 1)
        f0_rng = round(float(voiced.max() - voiced.min()), 1)
    else:
        f0_hz = f0_sd = f0_rng = 0.0

    def _num(v, scale=1.0, nd=3):
        v = float(v)
        return round(v * scale, nd) if math.isfinite(v) else ""

    pp = call(snd, "To PointProcess (periodic, cc)", fmin, fmax)
    jitter = _num(call(pp, "Get jitter (local)", 0, 0, 0.0001, 0.02, 1.3), 100.0)          # -> %
    shimmer = _num(call([snd, pp], "Get shimmer (local)", 0, 0, 0.0001, 0.02, 1.3, 1.6), 100.0)  # -> %
    hnr_obj = call(snd, "To Harmonicity (cc)", 0.01, fmin, 0.1, 1.0)
    hnr = _num(call(hnr_obj, "Get mean", 0, 0), 1.0, 1)                                     # -> dB
    return {"f0_hz": f0_hz, "f0_sd_hz": f0_sd, "f0_range_hz": f0_rng,
            "jitter": jitter, "shimmer": shimmer, "hnr": hnr}


def analyze_clip(path: Path, text: str = "") -> dict:
    """Measure one clip. Loudness (RMS dBFS) and speaking rate are ALWAYS numpy (one
    consistent scale); F0 and voice quality come from Praat/Parselmouth when available
    (backend='praat'), else the numpy autocorrelation fallback (backend='numpy', with the
    voice-quality fields left blank because numpy cannot compute them)."""
    x, sr = read_wav(path)
    dur = x.size / sr if sr else 0.0
    loud = round(rms_dbfs(x), 1)
    rate = round(len(text.split()) / dur, 2) if dur > 0 and text else 0.0

    f = {"f0_hz": 0.0, "f0_sd_hz": 0.0, "f0_range_hz": 0.0,
         "jitter": "", "shimmer": "", "hnr": "", "backend": "numpy"}
    if _HAVE_PRAAT:
        try:
            f.update(_praat_features(path))
            f["backend"] = "praat"
        except Exception:                        # pragma: no cover - degrade to numpy
            f = {"f0_hz": 0.0, "f0_sd_hz": 0.0, "f0_range_hz": 0.0,
                 "jitter": "", "shimmer": "", "hnr": "", "backend": "numpy"}
    if f["backend"] == "numpy":
        f.update(f0_stats(x, sr))                # f0_hz, f0_sd_hz, f0_range_hz from numpy

    return {
        "f0_hz": f["f0_hz"], "f0_sd_hz": f["f0_sd_hz"], "f0_range_hz": f["f0_range_hz"],
        "jitter": f["jitter"], "shimmer": f["shimmer"], "hnr": f["hnr"],
        "rms_dbfs": loud,
        "words_per_s": rate,
        "measured_dur_s": round(dur, 3),
        "backend": f["backend"],
        "silent": "yes" if loud <= SILENCE_DBFS else "no",
    }


MEASURED_COLS = ["f0_hz", "f0_sd_hz", "f0_range_hz", "jitter", "shimmer", "hnr",
                 "rms_dbfs", "words_per_s", "measured_dur_s", "backend", "silent"]


def _isnum(v) -> bool:
    try:
        return math.isfinite(float(v))
    except (TypeError, ValueError):
        return False


def _avg(vals) -> float:
    """Mean over numeric values only (blank / non-numeric entries are ignored)."""
    nums = [float(v) for v in vals if _isnum(v)]
    return mean(nums) if nums else 0.0


def _summary(rows: list[dict]) -> None:
    """Mean acoustics per (param_set, quadrant), audible clips only. Voice-quality columns
    (jitter/shimmer/HNR) are shown only when a backend actually produced them (i.e. Praat),
    so a numpy-fallback run does not print empty columns."""
    audible = [r for r in rows if r.get("silent") == "no"]
    if not audible:
        print("  (no audible clips to summarise -- run this on a REAL engine session, not mock)")
        return
    has_vq = any(_isnum(r.get("jitter")) for r in audible)
    groups: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for r in audible:
        groups[(r.get("param_set", "?"), r.get("quadrant", "?"))].append(r)
    print("\n== Mean acoustics per param_set x quadrant (audible clips) ==")
    head = f"  {'param_set':<18}{'quad':<6}{'F0 Hz':>8}{'F0 SD':>7}{'words/s':>9}{'RMS dB':>8}"
    if has_vq:
        head += f"{'jit %':>7}{'shim %':>8}{'HNR dB':>8}"
    print(head + f"{'n':>4}")
    for (ps, q) in sorted(groups):
        g = groups[(ps, q)]
        f0 = _avg([r["f0_hz"] for r in g if _isnum(r.get("f0_hz")) and float(r["f0_hz"]) > 0])
        line = (f"  {ps:<18}{q:<6}{f0:8.1f}{_avg([r.get('f0_sd_hz') for r in g]):7.1f}"
                f"{_avg([r.get('words_per_s') for r in g]):9.2f}{_avg([r.get('rms_dbfs') for r in g]):8.1f}")
        if has_vq:
            line += (f"{_avg([r.get('jitter') for r in g]):7.2f}"
                     f"{_avg([r.get('shimmer') for r in g]):8.2f}"
                     f"{_avg([r.get('hnr') for r in g]):8.1f}")
        print(line + f"{len(g):4d}")


def _before_after(rows: list[dict], before: str = "neutral", after: str = "rate_volume_pitch") -> None:
    """Objective Before/After: neutral baseline vs full emotion, per quadrant."""
    audible = [r for r in rows if r["silent"] == "no"]
    def cell(ps: str, q: str, key: str) -> float | None:
        vals = [r[key] for r in audible if r.get("param_set") == ps and r.get("quadrant") == q
                and _isnum(r.get(key)) and (key != "f0_hz" or float(r[key]) > 0)]
        return round(_avg(vals), 1) if vals else None
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


def _audio_path(raw: str) -> Path:
    """Cross-platform resolution of a register `audio_path` (Windows-written registers store
    backslashes, which are not separators on Linux/macOS). See build_register.resolve_audio_path."""
    return Path(str(raw).replace("\\", "/"))


def _resolve_out(path: Path, force: bool) -> Path:
    """Never overwrite: if the target already exists (and --force is not given), return a
    timestamped sibling (..._YYYYMMDD-HHMMSS[-n].csv) so no prior result is ever lost."""
    if force or not path.exists():
        return path
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    cand = path.with_name(f"{path.stem}_{stamp}{path.suffix}")
    i = 1
    while cand.exists():
        cand = path.with_name(f"{path.stem}_{stamp}-{i}{path.suffix}")
        i += 1
    return cand


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--register", default="research/register.csv",
                    help="register CSV to analyse (master or a session register.csv)")
    ap.add_argument("--out", default=None,
                    help="output CSV (default: acoustics.csv beside the register); never overwrites")
    ap.add_argument("--force", action="store_true", help="allow overwriting an existing --out")
    ap.add_argument("--before", default="neutral")
    ap.add_argument("--after", default="rate_volume_pitch")
    args = ap.parse_args(argv)

    src = Path(args.register)
    if not src.exists():
        print(f"Register not found: {src}. Build one first (build_register.py --build).")
        return 1

    measured, missing = [], 0
    for r in csv.DictReader(open(src, encoding="utf-8")):
        p = _audio_path(r.get("audio_path", ""))
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
    out = Path(args.out) if args.out else src.parent / "acoustics.csv"
    out = _resolve_out(out, args.force)
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
