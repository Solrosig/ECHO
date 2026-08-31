"""Parler-TTS runner — emotion as a natural-language DESCRIPTION (mechanism 5).

Parler-TTS has no CLI; it is a Python API (README, huggingface/parler-tts). This script is
the CLI, run inside Parler's own environment.

The description is the entire emotional channel. Parler was trained on synthetic annotations
describing speaker, pace, pitch and recording quality, so an instruction that mentions only
the emotion under-specifies the request and lets the model fill the rest arbitrarily. The
runner therefore appends a fixed **recording-quality and speaker clause** to ECHO's emotion
instruction: the emotional content varies across conditions, everything else is held
constant, and the constant part is stated here rather than buried in a prompt.
"""

from __future__ import annotations

import argparse
import sys

#: Held constant across every clip so the only thing that varies is the emotion. "very clear
#: audio" is the upstream README's documented lever for highest quality; naming one speaker
#: keeps voice identity fixed across quadrants, as the RAVDESS reference set does for the
#: reference-conditioned engines.
STYLE_SUFFIX = (" Jon speaks at a moderate speed. The recording is very clear audio, "
                "close up, with no background noise.")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--text", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--instruction", default="", help="ECHO's emotion instruction")
    ap.add_argument("--seed", type=int, default=666)
    ap.add_argument("--model-dir", default="", help="local weights if the HF hub is blocked")
    ap.add_argument("--model-id", default="parler-tts/parler-tts-mini-v1")
    args = ap.parse_args()

    try:
        import soundfile as sf
        import torch
        from parler_tts import ParlerTTSForConditionalGeneration
        from transformers import AutoTokenizer
    except Exception as exc:
        print(f"Parler-TTS not importable in this environment: {exc}\n"
              "Install it:  pip install git+https://github.com/huggingface/parler-tts.git",
              file=sys.stderr)
        return 2

    torch.manual_seed(args.seed)          # generation samples; the seed must be honoured
    device = "cuda:0" if torch.cuda.is_available() else "cpu"
    source = args.model_dir or args.model_id
    try:
        model = ParlerTTSForConditionalGeneration.from_pretrained(source).to(device)
        tokenizer = AutoTokenizer.from_pretrained(source)
    except Exception as exc:
        print(f"Could not load Parler-TTS from '{source}': {exc}\n"
              "If the Hugging Face hub is blocked, download parler-tts-mini-v1 in a browser "
              "and pass --model-dir.", file=sys.stderr)
        return 3

    description = (args.instruction.strip() + STYLE_SUFFIX).strip()
    input_ids = tokenizer(description, return_tensors="pt").input_ids.to(device)
    prompt_ids = tokenizer(args.text, return_tensors="pt").input_ids.to(device)
    audio = model.generate(input_ids=input_ids,
                           prompt_input_ids=prompt_ids).cpu().numpy().squeeze()
    sf.write(args.out, audio, model.config.sampling_rate)
    print(f"wrote {args.out}  ({len(audio)/model.config.sampling_rate:.2f}s)  "
          f"description: {description}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
