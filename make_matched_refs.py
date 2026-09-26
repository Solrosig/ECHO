"""Build a level-matched reference set, for engines that delete quiet audio.

Why: ZipVoice preprocesses its prompt with `remove_silence(..., silence_thresh=-50)`, a pydub
gate with an absolute threshold, applied before any normalisation. The RAVDESS reference set
spans roughly a 35x loudness range across quadrants because loudness is an arousal cue, and
the Q4 "calm" clip sits at about -52 dBFS RMS, under the gate. The engine classified almost
the whole reference as silence, conditioned on the surviving fragment, and emitted 0.10-0.21 s
of audio for every Q4 stimulus in both conditions rendered on 2026-08-31. Not a degraded
clip: no clip.

`check_refs.py` once made the same misjudgement, failing the RAVDESS set as "too quiet"; that
was overridden because the dynamic range is the signal. A validator refusing to certify data
is recoverable; an engine deleting it is not.

Output and cost: a new reference folder with every clip peak-normalised to a common target,
far above the gate. Each clip gets a single gain over its whole length and all four quadrants
get the same treatment, so within-clip dynamics, spectrum and timing are untouched. What is
removed is the between-quadrant loudness difference, i.e. the loudness component of the
arousal cue.

That cost is the point. Rendering against both sets gives a clean contrast:

    raw refs      -> Q1-Q3 usable, Q4 destroyed        (the engine's floor)
    matched refs  -> all four usable, no loudness cue  (the mechanism without loudness)

The difference isolates what the loudness cue contributed, which the original prediction
tried and failed to isolate with `--target-rms`.

The source set is never modified. A new folder is written, per the standing rule that results
and inputs move forward rather than being edited in place.

    python make_matched_refs.py                        # refs_ravdess -> refs_ravdess_matched
    python make_matched_refs.py --peak 0.5 --out refs_quiet_test
"""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

QUADRANTS = ("Q1", "Q2", "Q3", "Q4")

#: pydub's silence threshold inside ZipVoice's `remove_silence`, in dBFS. Hard-coded
#: upstream, so ECHO cannot configure it.
SILENCE_THRESH_DBFS = -50.0

#: Chunk length pydub uses when scanning for silence, in milliseconds.
_CHUNK_MS = 10


def dbfs(x: float) -> float:
    """Amplitude (0..1) -> dBFS. Silence maps to a large negative rather than -inf."""
    import math

    return 20.0 * math.log10(x) if x > 1e-12 else -120.0


def surviving_fraction(samples, sample_rate: int,
                       thresh_dbfs: float = SILENCE_THRESH_DBFS) -> float:
    """Share of 10 ms chunks louder than the silence threshold.

    Mirrors pydub, which compares each chunk's dBFS, rather than the clip's overall RMS,
    which misestimates a clip whose energy is unevenly distributed. A low value predicts
    that the engine will discard most of the reference as silence.
    """
    import numpy as np

    n = max(1, int(sample_rate * _CHUNK_MS / 1000))
    x = np.asarray(samples, dtype="float64")
    usable = (len(x) // n) * n
    if usable == 0:
        return 0.0
    chunks = x[:usable].reshape(-1, n)
    rms = np.sqrt((chunks ** 2).mean(axis=1))
    return float((rms > 10 ** (thresh_dbfs / 20.0)).mean())


def main(argv: "list[str] | None" = None) -> int:
    import numpy as np
    import soundfile as sf

    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--refs", default="refs_ravdess", help="source reference folder")
    ap.add_argument("--out", default="refs_ravdess_matched", help="destination folder")
    ap.add_argument("--peak", type=float, default=0.8,
                    help="common peak amplitude (0..1); 0.8 leaves headroom while sitting "
                         "far above the -50 dBFS gate")
    args = ap.parse_args(argv)

    src, dst = Path(args.refs), Path(args.out)
    if not src.is_dir():
        print(f"Source folder not found: {src}")
        return 1
    dst.mkdir(parents=True, exist_ok=True)

    print(f"Level-matching {src} -> {dst}   (target peak {args.peak})")
    print(f"Engine silence gate: {SILENCE_THRESH_DBFS:.0f} dBFS "
          f"(pydub, absolute, applied before any normalisation)\n")
    print(f"  {'ref':<5}{'peak in':>10}{'rms in':>10}{'survives':>10}   ->"
          f"{'peak out':>10}{'rms out':>10}{'survives':>10}")
    print("  " + "-" * 74)

    missing = 0
    for q in QUADRANTS:
        wav = src / f"{q}.wav"
        if not wav.exists():
            print(f"  {q:<5}MISSING")
            missing += 1
            continue
        x, sr = sf.read(str(wav), dtype="float32")
        if x.ndim > 1:
            x = x.mean(axis=1)
        peak_in = float(np.abs(x).max())
        rms_in = float(np.sqrt((x.astype("float64") ** 2).mean()))
        surv_in = surviving_fraction(x, sr)

        gain = (args.peak / peak_in) if peak_in > 1e-9 else 1.0
        y = np.clip(x.astype("float64") * gain, -1.0, 1.0).astype("float32")
        peak_out = float(np.abs(y).max())
        rms_out = float(np.sqrt((y.astype("float64") ** 2).mean()))
        surv_out = surviving_fraction(y, sr)

        sf.write(str(dst / f"{q}.wav"), y, sr, subtype="PCM_16")
        txt = wav.with_suffix(".txt")
        if txt.exists():
            shutil.copyfile(txt, dst / f"{q}.txt")     # zero-shot engines need the transcript
        else:
            print(f"  {q:<5}WARNING: no transcript beside {wav.name}")
            missing += 1

        flag = "  <- was below the gate" if surv_in < 0.2 else ""
        print(f"  {q:<5}{dbfs(peak_in):>9.1f}{dbfs(rms_in):>10.1f}{surv_in*100:>9.0f}%   ->"
              f"{dbfs(peak_out):>10.1f}{dbfs(rms_out):>10.1f}{surv_out*100:>9.0f}%{flag}")

    if missing:
        print(f"\n{missing} problem(s) — fix before rendering.")
        return 1

    print(f"\nWrote {len(QUADRANTS)} level-matched clips + transcripts to {dst}.")
    print("The between-quadrant loudness difference is now GONE by construction — that is")
    print("the manipulation, and it must be declared wherever this set is used.\n")
    print("Next:")
    print(f"  set ECHO_ZIPVOICE_REFS={dst}")
    print("  python check_zipvoice.py --quadrant Q4")
    print("  python synth_stimuli.py --engine zipvoice --param-set rate_volume_pitch "
          "--label zipvoice_b4_matched --purpose \"B4 condition 3: level-matched references "
          "- the mechanism with the loudness cue removed\"")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
