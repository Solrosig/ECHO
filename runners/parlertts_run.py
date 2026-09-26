"""Parler-TTS runner: emotion as a natural-language description (mechanism 5).

Parler-TTS has no CLI, only a Python API (README, huggingface/parler-tts). This script is
the CLI, run inside Parler's own environment.

The description is the entire emotional channel. Parler was trained on synthetic annotations
of speaker, pace, pitch and recording quality, so an emotion-only instruction under-specifies
the request and the model fills in the rest arbitrarily. The runner appends a fixed
recording-quality and speaker clause to ECHO's emotion instruction: the emotional content
varies across conditions, everything else is held constant, and the constant part is stated
here rather than buried in a prompt.
"""

from __future__ import annotations

import argparse
import sys

#: The style clause is part of the manipulation, not a constant, so it is a parameter.
#:
#: The first version (STYLE_SUFFIX_V1) was written to hold everything but the emotion
#: constant and did the opposite: "moderate speed" contradicts "agitated and tense", and
#: "very clear, close up" is the upstream README's recipe for clean read speech. A listener
#: check on 2026-08-31 confirmed the output was calm and fully intelligible. A control clause
#: that neutralises the variable under study is not a control.
#:
#: The default names only the speaker and the recording quality (no speed, no delivery),
#: leaving prosody entirely to the emotion clause.
STYLE_SUFFIX = " Jon is speaking. The recording is very clear audio, close up."

#: Retained for the record: the clause that cancelled the manipulation.
STYLE_SUFFIX_V1 = (" Jon speaks at a moderate speed. The recording is very clear audio, "
                   "close up, with no background noise.")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--text", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--instruction", default="", help="ECHO's emotion instruction")
    ap.add_argument("--seed", type=int, default=666)
    ap.add_argument("--model-dir", default="", help="local weights if the HF hub is blocked")
    ap.add_argument("--model-id", default="parler-tts/parler-tts-mini-v1")
    ap.add_argument("--style-suffix", default=STYLE_SUFFIX,
                    help="style clause appended to the emotion instruction; pass an empty "
                         "string to send the emotion instruction alone")
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

    description = (args.instruction.strip() + args.style_suffix).strip()
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
