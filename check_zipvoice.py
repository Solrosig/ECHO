"""Verify a ZipVoice installation AND prove filter T0.3 — reproducibility — empirically.

ZipVoice is a flow-matching model: it samples from noise, so it is stochastic by nature.
Every other neural engine in this project is deterministic, and the provenance store's
SHA-256 per clip silently assumes that a clip can be re-rendered identically. For ZipVoice
that assumption has to be DEMONSTRATED, not declared — a seed argument in the source proves
that the authors intended determinism, not that this installation delivers it.

So the check renders the same sentence three times through ECHO's own adapter:

    A = seed S        B = seed S        C = seed S+1

and compares the SHA-256 of each file:

    A == B   the seed pins the sampling  -> clips are reproducible, T0.3 SATISFIED
    A != B   identical inputs, different audio -> the provenance hash is meaningless, FAIL
    A == C   output ignores the seed entirely -> reproducible anyway; reported, not failed

The middle case is the one that matters and the only one that fails. The third is reported
honestly rather than treated as an error: an engine that produces the same audio whatever
the seed is MORE reproducible, not less, and mislabelling that as a failure would be the
same category of mistake as check_refs.py failing the RAVDESS set for having dynamics.

The check deliberately goes through `tts.ZipVoiceAdapter` rather than calling the ZipVoice
CLI directly, because what needs verifying is the path ECHO actually renders through —
including the seed the adapter passes. Verifying a different code path would prove nothing
about the one in use.

    python check_zipvoice.py                                   # defaults from config
    python check_zipvoice.py --python C:\\zipvoice\\.venv\\Scripts\\python.exe
    python check_zipvoice.py --quadrant Q2 --model zipvoice_distill

Exit code 0 = usable, 1 = not usable. Prints a Tier-1 latency figure as a by-product.
"""

from __future__ import annotations

import argparse
import hashlib
import time
import wave
from pathlib import Path

from config import load_config
from strategies import VoiceParams
from tts import ZipVoiceAdapter

#: A sentence with clear prosodic structure and no rare vocabulary, so a failure is
#: attributable to the engine rather than to an awkward input.
DEFAULT_TEXT = "I really did not expect to hear from you today."


def sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def wav_info(path: Path) -> "tuple[float, int] | None":
    """(duration_seconds, sample_rate), or None if the file is genuinely unreadable.

    `soundfile` is tried FIRST and `wave` only as a fallback, because the standard library's
    `wave` module reads integer PCM only and raises on float32 WAV — which is what
    `torchaudio.save` produces. Checking with `wave` alone reported a perfectly valid
    ZipVoice render as "not a valid WAV", which is this project's fourth instance of an
    instrument reporting a defect in something that was working: check_refs.py failing the
    RAVDESS set for having dynamics, quadrant thresholding erasing a real valence
    correlation, UTMOS mis-scoring paralinguistic tokens, and now this. When a check
    disagrees with an engine, the check is the more likely to be wrong.
    """
    try:
        import soundfile as sf

        info = sf.info(str(path))
        return info.frames / float(info.samplerate), info.samplerate
    except Exception:
        pass
    try:
        with wave.open(str(path), "rb") as w:
            return w.getnframes() / float(w.getframerate()), w.getframerate()
    except Exception:
        return None


def render(adapter: ZipVoiceAdapter, text: str, quadrant: str,
           out_path: Path) -> "tuple[Path, float]":
    """Render one clip through the adapter, returning the path and elapsed seconds.

    Volume is held at 1.0 on purpose: the adapter's loudness post-scale rewrites the file
    through soundfile, and that round-trip could introduce differences of its own. The
    engine's raw output is what is under test here.
    """
    vp = VoiceParams(voice_id="", rate=1.0, volume=1.0, pitch=1.0, quadrant=quadrant)
    start = time.perf_counter()
    adapter.synthesize(text, vp, out_path)
    return out_path, time.perf_counter() - start


def main(argv: "list[str] | None" = None) -> int:
    cfg = load_config()
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--python", default=cfg.zipvoice_python,
                    help="interpreter of the ZipVoice environment (default: from config)")
    ap.add_argument("--refs", default=cfg.zipvoice_refs, help="per-quadrant reference folder")
    ap.add_argument("--quadrant", default="Q1", choices=["Q1", "Q2", "Q3", "Q4"])
    ap.add_argument("--model", default=cfg.zipvoice_model,
                    help="zipvoice | zipvoice_distill")
    ap.add_argument("--model-dir", default=cfg.zipvoice_model_dir)
    ap.add_argument("--repo", default=cfg.zipvoice_repo,
                    help="the ZipVoice checkout (it ships no setup.py, so the package is "
                         "not importable without this)")
    ap.add_argument("--vocoder", default=cfg.zipvoice_vocoder,
                    help="local vocos-mel-24khz folder (separate HF repo)")
    ap.add_argument("--seed", type=int, default=cfg.zipvoice_seed)
    ap.add_argument("--text", default=DEFAULT_TEXT)
    ap.add_argument("--out", default="research/zipvoice_check",
                    help="where the three probe clips are written (kept, never overwritten)")
    args = ap.parse_args(argv)

    print("ZipVoice installation and reproducibility check")
    print("=" * 70)

    # --- 1. references ----------------------------------------------------
    refs = Path(args.refs)
    wav, txt = refs / f"{args.quadrant}.wav", refs / f"{args.quadrant}.txt"
    print(f"\n1. Reference set  ({refs})")
    if not wav.exists():
        print(f"   FAIL  {wav} not found.")
        print("   Fix:  python make_ravdess_refs.py --ravdess <RAVDESS folder> --actor 1")
        return 1
    if not txt.exists():
        print(f"   FAIL  {txt} not found — ZipVoice needs the transcript, not only the clip.")
        print("   Fix:  re-run make_ravdess_refs.py (it now writes Q1.txt..Q4.txt)")
        return 1
    print(f"   OK    {wav.name} + {txt.name}   \"{txt.read_text(encoding='utf-8').strip()}\"")

    # --- 2. three renders -------------------------------------------------
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")            # never overwrite a previous check
    interpreter = args.python or "(this interpreter)"
    print(f"\n2. Rendering three probe clips   [model={args.model}, interpreter={interpreter}]")
    print(f"   repo: {args.repo or 'NOT SET — zipvoice must already be importable'}")
    print(f"   text: \"{args.text}\"")
    print("   The first render loads the model (and may download it) — please wait.")

    def adapter_with(seed: int) -> ZipVoiceAdapter:
        # Every setting the render depends on must be passed here. This function is the
        # second place config is mapped onto the adapter (make_tts is the first), and that
        # duplication has already cost one failed run: `repo` was added to the adapter and
        # to make_tts but not here, so the check ran without a PYTHONPATH and reported a
        # missing module that was in fact present.
        return ZipVoiceAdapter(refs_dir=str(refs), python=args.python, model_name=args.model,
                               model_dir=args.model_dir, seed=seed,
                               num_step=cfg.zipvoice_num_step,
                               target_rms=cfg.zipvoice_target_rms,
                               num_thread=cfg.zipvoice_threads,
                               repo=args.repo, vocoder_dir=args.vocoder)

    plan = [("A", args.seed), ("B", args.seed), ("C", args.seed + 1)]
    results: dict[str, tuple[Path, float, str]] = {}
    for name, seed in plan:
        path = out_dir / f"{stamp}_{args.quadrant}_{name}_seed{seed}.wav"
        try:
            path, elapsed = render(adapter_with(seed), args.text, args.quadrant, path)
        except RuntimeError as exc:
            print(f"\n   FAIL  render {name} (seed {seed}) did not complete:\n")
            for line in str(exc).splitlines():
                print(f"         {line}")
            return 1
        digest = sha256_of(path)
        info = wav_info(path)
        shape = (f"{info[0]:.2f}s @ {info[1]} Hz" if info else "UNREADABLE — not a valid WAV")
        print(f"   {name}  seed {seed:<6} {elapsed:6.1f}s   {shape}   sha {digest[:12]}")
        results[name] = (path, elapsed, digest)
        if info is None:
            print("   FAIL  the engine wrote a file that is not a readable WAV.")
            return 1

    # --- 3. verdict -------------------------------------------------------
    a, b, c = (results[k][2] for k in ("A", "B", "C"))
    print("\n3. Reproducibility (filter T0.3)")
    if a != b:
        print("   FAIL  Same seed, same text, DIFFERENT audio.")
        print("         Clips cannot be re-rendered, so the provenance SHA-256 records a")
        print("         one-off artefact rather than a reproducible result. Do not use this")
        print("         engine for reported measurements until this is resolved.")
        return 1
    print("   OK    Same seed reproduces the clip byte-for-byte (A == B).")
    if a == c:
        print("   NOTE  A different seed produced identical audio, so this configuration is")
        print("         deterministic regardless of the seed. That is stronger than required;")
        print("         the seed is still recorded, because a future version may not be.")
    else:
        print("   OK    A different seed changes the audio (A != C) — the seed is genuinely")
        print("         what pins the sampling, so pinning it is doing real work.")

    # --- 4. latency, as a Tier-1 by-product -------------------------------
    warm = (results["B"][1] + results["C"][1]) / 2.0
    print("\n4. Latency (Tier 1 'latency' metric — seconds per clip)")
    print(f"   first render {results['A'][1]:.1f}s (includes model load)"
          f" · warm mean {warm:.1f}s over 2 clips")
    if warm > 60:
        print("   NOTE  Slow. Each clip pays a fresh model load because the adapter runs")
        print("         out of process. For a full corpus try --model zipvoice_distill and")
        print("         ECHO_ZIPVOICE_STEPS=4, then re-run this check to confirm T0.3 holds")
        print("         for that configuration too.")

    print(f"\nProbe clips kept in {out_dir} (timestamped, never overwritten).")
    print("VERDICT: ZipVoice is installed and reproducible — usable for reported measurements.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
