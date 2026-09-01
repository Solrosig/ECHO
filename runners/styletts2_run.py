"""StyleTTS 2 runner — emotion as an explicit STYLE VECTOR (mechanism 4).

StyleTTS 2 (Li et al., NeurIPS 2023) ships notebooks rather than a CLI. The community
`styletts2` package wraps the reference implementation with a stable inference call, which is
what this runner uses; the upstream repository remains the citable artefact.

The style vector is what makes this engine mechanism 4 rather than another reference-transfer
engine: it can be **extracted from a reference clip** (what ECHO does here, so the comparison
against Chatterbox and ZipVoice holds the reference constant) or **sampled from a diffusion
model**, which would produce a style ECHO never supplied. Only the first is used for the
paired corpus; the second is noted as available and unused, because a sampled style has no
declared target and could not be scored against one.
"""

from __future__ import annotations

import argparse
import sys


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--text", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--ref-wav", default="", help="clip the style vector is extracted from")
    ap.add_argument("--seed", type=int, default=666)
    ap.add_argument("--model-dir", default="", help="local checkpoint + config")
    args = ap.parse_args()

    try:
        import torch
        from styletts2 import tts as styletts2_tts
    except Exception as exc:
        print(f"StyleTTS 2 not importable in this environment: {exc}\n"
              "Install it:  pip install styletts2  (wraps yl4579/StyleTTS2)", file=sys.stderr)
        return 2

    torch.manual_seed(args.seed)
    try:
        kwargs = {}
        if args.model_dir:
            kwargs["model_checkpoint_path"] = args.model_dir
        model = styletts2_tts.StyleTTS2(**kwargs)
    except Exception as exc:
        print(f"Could not load StyleTTS 2: {exc}\n"
              "If the Hugging Face hub is blocked, download the checkpoint and config in a "
              "browser and pass --model-dir.", file=sys.stderr)
        return 3

    try:
        model.inference(args.text,
                        target_voice_path=args.ref_wav or None,
                        output_wav_file=args.out)
    except Exception as exc:
        print(f"StyleTTS 2 inference failed: {exc}", file=sys.stderr)
        return 4
    print(f"wrote {args.out}  style from: {args.ref_wav or '(default voice)'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
