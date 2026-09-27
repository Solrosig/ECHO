"""Acoustic analysis, version 2 — literature-anchored measurement of the frozen corpus.

WHAT CHANGED AND WHY (each change answers a specific methodological objection):

1.  F0 IN SEMITONES, NOT HERTZ.
    The nine configurations use nine different voices, with base F0 from roughly 100 Hz
    to roughly 220 Hz.  A difference of 20 Hz means something different on a low voice
    than on a high one, because pitch perception is approximately logarithmic.  The
    Geneva Minimalistic Acoustic Parameter Set therefore specifies F0 on a semitone
    scale from 27.5 Hz, and every cross-speaker comparison here follows it.
        Eyben, F., Scherer, K. R., Schuller, B. W., Sundberg, J., Andre, E., Busso, C.,
        Devillers, L. Y., Epps, J., Laukka, P., Narayanan, S. S., & Truong, K. P. (2016).
        The Geneva Minimalistic Acoustic Parameter Set (GeMAPS) for voice research and
        affective computing.  IEEE Transactions on Affective Computing, 7(2), 190-202.

2.  ARTICULATION RATE SEPARATED FROM SPEECH RATE.
    Words per second confounds speaking speed with pausing, because an engine that
    inserts long silences scores as "slow" even when its syllables are fast.  Speech
    rate is therefore computed over total duration and articulation rate over phonation
    time only, with pause fraction reported alongside.  The silence threshold of 25 dB
    below peak, the minimum pause of 0.30 s and the speech-rate/articulation-rate
    distinction are the declared defaults of the distributed Syllable Nuclei script.
        de Jong, N. H., & Wempe, T. (2009).  Praat script to detect syllable nuclei and
        measure speech rate automatically.  Behavior Research Methods, 41(2), 385-390.
        de Jong, N. H., Pacilly, J., & Heeren, W. (2021).  PRAAT scripts to measure speed
        fluency and breakdown fluency in speech automatically.  Assessment in Education:
        Principles, Policy & Practice, 28(4), 456-476.
    DECLARED DEVIATION: syllable count is taken from the fixed carrier text rather than
    from intensity-peak nuclei detection, so the minimum-dip criterion is not applied.
    The carrier text is identical for all 45 clips, therefore the syllable count is a
    constant and cancels from every within-configuration delta.  Articulation rate here
    is consequently phonation time re-expressed with a constant numerator, not an
    independent estimate of syllable nuclei.

3.  LOUDNESS IS DROPPED FOR THE FROZEN CORPUS, AND SAID SO.
    The 45 frozen clips were level-normalised to a common active RMS of -24.44 dBFS
    before the listening test.  Any loudness measure on that corpus is therefore a
    measure of the normaliser, not of the engine.  Dynamic range (the spread of
    short-term loudness within a clip) survives normalisation and is measured instead.

4.  VOICE QUALITY IS KEPT AND FOREGROUNDED.
    Jitter, shimmer and harmonics-to-noise ratio are the valence-relevant channel that
    F0 and rate do not carry, and the meta-analysis of vocal emotion cues identifies
    voice quality as central to emotions that share an arousal level.
        Juslin, P. N., & Laukka, P. (2003).  Communication of emotions in vocal expression
        and music performance: Different channels, same code?  Psychological Bulletin,
        129(5), 770-814.
    F0 and harmonics-to-noise ratio are computed by the autocorrelation method.
        Boersma, P. (1993).  Accurate short-term analysis of the fundamental frequency and
        the harmonics-to-noise ratio of a sampled sound.  IFA Proceedings, 17, 97-110.

5.  EVERY MEASURE IS REPORTED AS A WITHIN-CONFIGURATION DELTA.
    A preset is compared with the matched neutral rendition of its own configuration,
    never with an absolute reference.  This is the same paired logic the listener
    analysis uses, and it removes the default character of each voice from the
    comparison.

    python analyze_acoustics_v2.py --register research/register_frozen45.csv

Outputs (beside the register):
    acoustics_v2_per_clip.csv     one row per clip, raw measures
    acoustics_v2_deltas.csv       preset minus matched neutral, per configuration and target
    acoustics_v2_summary.txt      the printed report
"""
from __future__ import annotations

import argparse
import csv
import math
import sys
import wave
from pathlib import Path

import numpy as np

try:
    import parselmouth
    from parselmouth.praat import call
    HAVE_PRAAT = True
except Exception:
    HAVE_PRAAT = False

F0_MIN, F0_MAX = 75.0, 400.0          # speaking-voice band
SEMITONE_REF = 27.5                   # GeMAPS reference, Hz
SIL_REL_DB = 25.0                     # de Jong & Wempe: silence threshold below peak
MIN_PAUSE_S = 0.30                    # de Jong & Wempe: minimum pause duration
OUT: list[str] = []


def say(*a):
    line = " ".join(str(x) for x in a)
    print(line)
    OUT.append(line)


def st(hz: float) -> float:
    """Hz to semitones above 27.5 Hz (GeMAPS convention)."""
    return 12.0 * math.log2(hz / SEMITONE_REF) if hz and hz > 0 else float("nan")


def read_wav(p: Path):
    with contextlib_closing(wave.open(str(p), "rb")) as w:
        sr, n, sw, ch = w.getframerate(), w.getnframes(), w.getsampwidth(), w.getnchannels()
        raw = w.readframes(n)
    dt = {1: np.uint8, 2: np.int16, 4: np.int32}[sw]
    x = np.frombuffer(raw, dtype=dt).astype(np.float64)
    x = (x - 128.0) / 128.0 if sw == 1 else x / float(2 ** (8 * sw - 1))
    if ch > 1:
        x = x.reshape(-1, ch).mean(axis=1)
    return x, sr


class contextlib_closing:
    def __init__(self, thing): self.thing = thing
    def __enter__(self): return self.thing
    def __exit__(self, *a): self.thing.close()


def envelope_db(x: np.ndarray, sr: int, win_s: float = 0.02):
    """Short-term RMS envelope in dB, 20 ms windows, 10 ms hop."""
    w, h = int(win_s * sr), int(win_s * sr / 2)
    if len(x) < w:
        return np.array([]), h / sr
    frames = np.lib.stride_tricks.sliding_window_view(x, w)[::h]
    rms = np.sqrt((frames ** 2).mean(axis=1) + 1e-12)
    return 20 * np.log10(rms + 1e-12), h / sr


def rate_measures(x: np.ndarray, sr: int, n_syllables: int | None = None):
    """Speech rate, articulation rate and pause fraction.

    Follows the de Jong & Wempe (2009) logic: a relative silence threshold below the
    peak, a minimum pause duration, and articulation rate computed over phonation time
    only.  Syllable count comes from the fixed carrier text, so the only quantity
    estimated from the signal is where the speech is.
    """
    env, hop = envelope_db(x, sr)
    if env.size == 0:
        return dict(dur_s=len(x) / sr, phonation_s=float("nan"),
                    pause_fraction=float("nan"), speech_rate=float("nan"),
                    articulation_rate=float("nan"), n_pauses=float("nan"))
    thr = env.max() - SIL_REL_DB
    voiced = env > thr
    dur = len(x) / sr
    phon = voiced.sum() * hop
    # count runs of silence at least MIN_PAUSE_S long, excluding leading/trailing
    runs, cur = [], 0
    for v in voiced:
        if not v:
            cur += 1
        elif cur:
            runs.append(cur); cur = 0
    n_pause = sum(1 for r in runs if r * hop >= MIN_PAUSE_S)
    d = dict(dur_s=round(dur, 3), phonation_s=round(phon, 3),
             pause_fraction=round(1 - phon / dur, 4) if dur else float("nan"),
             n_pauses=n_pause)
    if n_syllables:
        d["speech_rate"] = round(n_syllables / dur, 3) if dur else float("nan")
        d["articulation_rate"] = round(n_syllables / phon, 3) if phon else float("nan")
    return d


def praat_measures(path: Path):
    """F0 level and spread in semitones, voice quality, dynamic range."""
    snd = parselmouth.Sound(str(path))
    pitch = snd.to_pitch(pitch_floor=F0_MIN, pitch_ceiling=F0_MAX)
    f = pitch.selected_array["frequency"]
    f = f[f > 0]
    out = {}
    if f.size:
        sem = np.array([st(v) for v in f])
        out.update(f0_median_hz=round(float(np.median(f)), 2),
                   f0_median_st=round(float(np.median(sem)), 3),
                   f0_sd_st=round(float(np.std(sem, ddof=1)), 3) if f.size > 1 else float("nan"),
                   f0_range_st=round(float(np.percentile(sem, 95) - np.percentile(sem, 5)), 3),
                   f0_p20_p80_st=round(float(np.percentile(sem, 80) - np.percentile(sem, 20)), 3),
                   voiced_fraction=round(float(f.size / max(1, pitch.get_number_of_frames())), 4))
    try:
        pp = call(snd, "To PointProcess (periodic, cc)", F0_MIN, F0_MAX)
        out["jitter_local_pct"] = round(call(pp, "Get jitter (local)", 0, 0, 1e-4, 0.02, 1.3) * 100, 4)
        out["shimmer_local_pct"] = round(
            call([snd, pp], "Get shimmer (local)", 0, 0, 1e-4, 0.02, 1.3, 1.6) * 100, 4)
        h = call(snd, "To Harmonicity (cc)", 0.01, F0_MIN, 0.1, 1.0)
        out["hnr_db"] = round(call(h, "Get mean", 0, 0), 3)
    except Exception:
        pass
    return out


def syllables(text: str) -> int:
    """Crude English syllable count. The carrier text is fixed, so this constant is the
    same for every clip and cancels out of every within-configuration comparison."""
    t = "".join(c.lower() if c.isalpha() or c.isspace() else " " for c in text)
    n = 0
    for w in t.split():
        v = "aeiouy"
        c = sum(1 for i, ch in enumerate(w) if ch in v and (i == 0 or w[i - 1] not in v))
        if w.endswith("e") and c > 1:
            c -= 1
        n += max(1, c)
    return n


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--register", default="research/register_frozen45.csv")
    ap.add_argument("--out-dir", default=None)
    args = ap.parse_args(argv)

    src = Path(args.register)
    if not src.exists():
        sys.exit(f"Register not found: {src}")
    out_dir = Path(args.out_dir) if args.out_dir else src.parent
    rows = list(csv.DictReader(open(src, encoding="utf-8")))

    say(f"Praat backend: {'parselmouth' if HAVE_PRAAT else 'ABSENT — voice quality unavailable'}")
    say(f"register: {src}  ({len(rows)} clips)\n")

    measured, missing = [], 0
    for r in rows:
        p = Path(str(r.get("audio_path", "")).replace("\\", "/"))
        if not p.exists():
            missing += 1
            continue
        x, sr = read_wav(p)
        m = dict(r)
        nsyl = syllables(r.get("text", "")) or None
        m.update(rate_measures(x, sr, nsyl))
        m["n_syllables"] = nsyl
        env, _ = envelope_db(x, sr)
        if env.size:
            v = env[env > env.max() - SIL_REL_DB]
            m["dynamic_range_db"] = round(float(np.percentile(v, 95) - np.percentile(v, 5)), 3)
        if HAVE_PRAAT:
            m.update(praat_measures(p))
        measured.append(m)

    if not measured:
        sys.exit(f"No clips found on disk from {src} ({missing} missing).")
    say(f"measured {len(measured)} clips ({missing} missing)\n")

    fields = list(dict.fromkeys(k for m in measured for k in m))
    per_clip = out_dir / "acoustics_v2_per_clip.csv"
    with open(per_clip, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader(); w.writerows(measured)

    # ---------- within-configuration deltas ----------
    MEAS = ["f0_median_st", "f0_sd_st", "f0_range_st", "f0_p20_p80_st",
            "articulation_rate", "speech_rate",
            "pause_fraction", "jitter_local_pct", "shimmer_local_pct", "hnr_db",
            "dynamic_range_db", "dur_s"]
    by_eng_cond = {}
    for m in measured:
        by_eng_cond[(m["engine"], m["param_set"], m.get("emotion", ""))] = m

    deltas = []
    for (eng, ps, emo), m in by_eng_cond.items():
        if ps != "preset":
            continue
        base = by_eng_cond.get((eng, "neutral", "neutral"))
        if not base:
            continue
        d = dict(engine=eng, emotion=emo)
        for k in MEAS:
            a, b = m.get(k), base.get(k)
            try:
                d["d_" + k] = round(float(a) - float(b), 4)
            except (TypeError, ValueError):
                d["d_" + k] = ""
        deltas.append(d)

    if deltas:
        dpath = out_dir / "acoustics_v2_deltas.csv"
        dfields = list(dict.fromkeys(k for d in deltas for k in d))
        with open(dpath, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=dfields)
            w.writeheader(); w.writerows(deltas)

        say("=" * 88)
        say("PRESET MINUS MATCHED NEUTRAL, per configuration  (semitones, syll/s, %, dB)")
        say("=" * 88)
        hdr = f"{'engine':<12}{'target':<8}" + "".join(
            f"{h:>12}" for h in ["dF0 (st)", "dF0rng(st)", "dArtRate", "dJitter%", "dHNR dB"])
        say(hdr)
        for d in sorted(deltas, key=lambda z: (z["engine"], z["emotion"])):
            def g(k):
                v = d.get("d_" + k, "")
                return f"{v:>12.2f}" if isinstance(v, float) else f"{'-':>12}"
            say(f"{d['engine']:<12}{d['emotion']:<8}"
                + g("f0_median_st") + g("f0_range_st") + g("articulation_rate")
                + g("jitter_local_pct") + g("hnr_db"))

        # direction check against the meta-analytic expectation
        say("")
        say("=" * 88)
        say("DIRECTION CHECK  (Juslin & Laukka 2003: high-arousal targets raise F0 and rate)")
        say("=" * 88)
        HIGH = {"happy", "upset"}
        for k, label in [("f0_median_st", "F0 level"), ("articulation_rate", "articulation rate")]:
            hi = [d["d_" + k] for d in deltas if d["emotion"] in HIGH and isinstance(d.get("d_" + k), float)]
            lo = [d["d_" + k] for d in deltas if d["emotion"] not in HIGH and isinstance(d.get("d_" + k), float)]
            if hi and lo:
                say(f"  {label:20s} high-arousal targets {np.mean(hi):+7.3f}   "
                    f"low-arousal targets {np.mean(lo):+7.3f}   "
                    f"separation {np.mean(hi) - np.mean(lo):+7.3f}")

    (out_dir / "acoustics_v2_summary.txt").write_text("\n".join(OUT), encoding="utf-8")
    say(f"\nwritten: {per_clip.name}"
        + (f" · acoustics_v2_deltas.csv" if deltas else "")
        + " · acoustics_v2_summary.txt")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
