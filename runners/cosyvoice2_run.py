"""CosyVoice 2 runner — emotion as a natural-language INSTRUCTION (mechanism 5).

CosyVoice 2 has no CLI; it is a Python API (FunAudioLLM/CosyVoice). This script is the CLI,
run inside CosyVoice's own environment.

`inference_instruct2` is the instruction-conditioned entry point and takes a prompt clip in
addition to the instruction, because the model separates *who is speaking* (the clip) from
*how they speak it* (the instruction). ECHO supplies the same per-quadrant reference set the
other engines use, which keeps voice identity constant and lets the instruction carry the
emotion alone.

If upstream renames or re-signatures that function, **this file is the only thing to change** —
the adapter, the config and the tests are unaffected.
"""

from __future__ import annotations

import argparse
import sys


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--text", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--instruction", default="")
    ap.add_argument("--ref-wav", default="", help="prompt clip: fixes WHO speaks")
    ap.add_argument("--seed", type=int, default=666)
    ap.add_argument("--model-dir", default="pretrained_models/CosyVoice2-0.5B")
    args = ap.parse_args()

    try:
        import torch
        import torchaudio
        from cosyvoice.cli.cosyvoice import CosyVoice2
        from cosyvoice.utils.file_utils import load_wav
    except Exception as exc:
        print(f"CosyVoice not importable in this environment: {exc}\n"
              "It ships no setup.py — clone it and put the checkout on PYTHONPATH "
              "(ECHO_COSYVOICE2_REPO), then pip install -r requirements.txt.",
              file=sys.stderr)
        return 2

    torch.manual_seed(args.seed)
    try:
        model = CosyVoice2(args.model_dir)
    except Exception as exc:
        print(f"Could not load CosyVoice2 from '{args.model_dir}': {exc}\n"
              "Download CosyVoice2-0.5B (Apache-2.0) and pass --model-dir.", file=sys.stderr)
        return 3

    if not args.ref_wav:
        print("CosyVoice2 inference_instruct2 needs a prompt clip (--ref-wav): the clip fixes "
              "WHO speaks, the instruction fixes HOW.", file=sys.stderr)
        return 4

    prompt = load_wav(args.ref_wav, 16000)
    chunks = [o["tts_speech"] for o in model.inference_instruct2(
        args.text, args.instruction, prompt, stream=False)]
    if not chunks:
        print("CosyVoice2 returned no audio.", file=sys.stderr)
        return 5
    audio = torch.cat(chunks, dim=1) if len(chunks) > 1 else chunks[0]
    torchaudio.save(args.out, audio, model.sample_rate)
    print(f"wrote {args.out}  instruction: {args.instruction}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
