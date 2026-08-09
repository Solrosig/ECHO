"""Objective emotion conveyance (Story N5): does a machine listener recover the emotion
ECHO intended — and how does that trade off against naturalness across engines?

Closes the synthesis -> recognition loop. A pretrained *dimensional* speech-emotion
recogniser (audeering wav2vec2-large-robust-12-ft-emotion-msp-dim; Wagner et al., 2023,
IEEE TPAMI) predicts arousal / dominance / valence straight from each clip. We map its
0..1 outputs to ECHO's [-1,1] axes, derive the predicted quadrant, and compare with the
INTENDED quadrant, reporting per engine:
  * quadrant accuracy (4-class; chance = 25 %) and arousal/valence sign accuracy,
  * Spearman agreement between intended and recognised arousal and valence,
  * a confusion matrix (intended -> recognised).

Read with the documented VALENCE GAP caveat: acoustic valence is intrinsically hard, so
recognisers are far stronger on arousal than valence (Wagner et al., 2023) — low valence
agreement is partly a property of the recogniser, not only of ECHO's rendering. This is the
machine proxy for the human 4-AFC test (S1), which remains the ground truth.

    python emotion_conveyance.py --register research/register.csv
        -> emotion.csv beside the register (never overwrites) + per-engine report

torch/transformers are OPTIONAL eval-layer deps (`pip install torch transformers librosa`);
the model downloads from Hugging Face on first use, or loads from a local folder via
`--model` / `ECHO_SER_MODEL` (needed where TLS to huggingface.co is filtered).

PORTABILITY NOTES (hard-won; see PROJECT_LOG "FIXING CHAIN" 2026-07-27). This module
deliberately does NOT use the model card's published loading code, because it breaks on
current libraries. Three deviations, each with a reason:
  1. No `Wav2Vec2Processor` — it needs `processor_config.json`, absent from this (4.x-era)
     repo, so transformers 5.x cannot build it. The processor only does zero-mean/unit-
     variance normalisation, which `predict_va()` applies inline instead.
  2. `EmotionModel` is a plain `nn.Module`, NOT a `Wav2Vec2PreTrainedModel` — the parent
     class drags in `init_weights()`/`tie_weights()`, which in transformers 5.x require an
     `all_tied_weights_keys` attribute the 4.x-era class never defined (it failed at
     construction, even offline). Module names are unchanged, so the published checkpoint
     still loads as-is.
  3. Weights are read with plain `load_state_dict` (`_load_state_dict()`), not
     `from_pretrained` — fewer moving parts, no version-specific finaliser.
The net effect: this runs on transformers 4.x and 5.x, online or fully offline.
"""

from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from statistics import mean

import os

MODEL_ID = os.getenv("ECHO_SER_MODEL", "audeering/wav2vec2-large-robust-12-ft-emotion-msp-dim")
_MODEL = None
SR = 16000                      # the model expects 16 kHz mono


def _load_model(model_id: str | None = None):
    """Lazy-load the dimensional SER model (torch + transformers), with clear errors.

    `model_id` may be the Hugging Face repo id OR a LOCAL directory containing the model
    files (config.json + weights) — set via --model / ECHO_SER_MODEL. The local option
    exists because networks that filter TLS often block the Hugging Face download.
    """
    global _MODEL
    if _MODEL is None:
        try:
            import torch  # noqa: F401
            from transformers.models.wav2vec2.modeling_wav2vec2 import Wav2Vec2Model
            import torch.nn as nn
        except Exception as exc:
            raise RuntimeError(
                "Emotion conveyance needs torch + transformers — eval-only extras: "
                "`pip install torch transformers` (CPU wheels are fine)."
            ) from exc

        class RegressionHead(nn.Module):
            def __init__(self, config):
                super().__init__()
                self.dense = nn.Linear(config.hidden_size, config.hidden_size)
                self.dropout = nn.Dropout(config.final_dropout)
                self.out_proj = nn.Linear(config.hidden_size, config.num_labels)

            def forward(self, features):
                x = self.dropout(torch.tanh(self.dense(features)))
                return self.out_proj(x)

        class EmotionModel(nn.Module):
            """wav2vec2 + regression head -> (arousal, dominance, valence).

            Deliberately a PLAIN `nn.Module`, not a `Wav2Vec2PreTrainedModel`: the model card's
            4.x-era class routes through transformers' pretrained machinery (`init_weights` ->
            `tie_weights` -> `all_tied_weights_keys`), which changed in 5.x and breaks. We only
            need the architecture plus a state dict, and the submodule names (`wav2vec2.*`,
            `classifier.*`) are identical, so the published checkpoint loads unchanged — and
            this stays stable across transformers versions.
            """

            def __init__(self, config):
                super().__init__()
                self.config = config
                self.wav2vec2 = Wav2Vec2Model(config)
                self.classifier = RegressionHead(config)

            def forward(self, input_values):
                hidden = self.wav2vec2(input_values)[0]
                return self.classifier(torch.mean(hidden, dim=1))

        src = model_id or MODEL_ID
        # A local dir is only usable if it actually holds the model files. An EMPTY or partial
        # folder (e.g. the weights were deleted to reclaim disk space) previously surfaced as
        # "Unrecognized model in ser_model" — so fall back to the hub id, which resolves from the
        # local HF cache when the model has been downloaded once.
        if src != MODEL_ID and not (Path(src) / "config.json").exists():
            print(f"  (note: '{src}' has no config.json — falling back to '{MODEL_ID}' "
                  "via the Hugging Face cache)")
            src = MODEL_ID
        try:
            # Build from config + load weights DIRECTLY, bypassing from_pretrained():
            # transformers 5.x's loading finalizer expects attributes (all_tied_weights_keys)
            # that this custom model class (written for 4.x) does not define.
            # Wav2Vec2Config (explicit) rather than AutoConfig: auto-detection needs a
            # `model_type` key and its strictness varies across transformers versions.
            from transformers import Wav2Vec2Config as _Cfg
            cfg = _Cfg.from_pretrained(src)
            model = EmotionModel(cfg)
            state = _load_state_dict(src)
            result = model.load_state_dict(state, strict=False)
            # SAFETY GUARD: strict=False tolerates key mismatches (needed, since the checkpoint
            # carries training-only tensors), but that also means a WRONG checkpoint would load
            # silently and the model would emit plausible-looking, meaningless scores — the worst
            # failure mode for a research tool. So require the regression head explicitly.
            loaded = [k for k in state if k.startswith("classifier.")]
            if not loaded:
                raise RuntimeError("checkpoint has no 'classifier.*' weights (wrong model?)")
            missing = [k for k in getattr(result, "missing_keys", []) if not k.startswith("wav2vec2.masked_spec_embed")]
            if missing:
                print(f"  (note: {len(missing)} weight(s) not found in the checkpoint; "
                      f"first: {missing[:3]})")
            _MODEL = model.eval()
        except Exception as exc:
            raise RuntimeError(
                f"Could not load the SER model '{src}': {exc}\n"
                "If the Hugging Face download is blocked by your network (TLS reset / "
                "WinError 10054), download the model files once in a BROWSER from\n"
                "  https://huggingface.co/audeering/wav2vec2-large-robust-12-ft-emotion-msp-dim/tree/main\n"
                "(config.json + model.safetensors or pytorch_model.bin) into a folder, then pass\n"
                "  --model C:\\path\\to\\that\\folder   (or set ECHO_SER_MODEL)."
            ) from exc
    return _MODEL


def _load_state_dict(src: str) -> dict:
    """Read the weights from a local folder (preferred) or fetch them from the HF hub."""
    import torch

    local = Path(src)
    if local.is_dir():
        st, bin_ = local / "model.safetensors", local / "pytorch_model.bin"
        if st.exists():
            from safetensors.torch import load_file
            return load_file(str(st))
        if bin_.exists():
            return torch.load(str(bin_), map_location="cpu", weights_only=True)
        raise RuntimeError(f"no model.safetensors or pytorch_model.bin in {local}")

    from huggingface_hub import hf_hub_download
    try:
        from safetensors.torch import load_file
        return load_file(hf_hub_download(src, "model.safetensors"))
    except Exception:
        return torch.load(hf_hub_download(src, "pytorch_model.bin"),
                          map_location="cpu", weights_only=True)


def predict_va(wav_path, model_id: str | None = None) -> dict:
    """Recognised emotion for one clip, on ECHO's axes: valence/arousal in [-1, 1].

    The audeering processor only does zero-mean/unit-variance normalisation, so we apply it
    directly — avoiding a second network fetch (and processor_config.json incompatibilities
    across transformers versions)."""
    import librosa
    import numpy as np
    import torch

    model = _load_model(model_id)
    wave, _ = librosa.load(str(wav_path), sr=SR, mono=True)
    # FIX (see docstring note 1): this line replaces Wav2Vec2Processor entirely. The audeering
    # processor is configured with do_normalize=True and nothing else, so zero-mean/unit-variance
    # IS its whole behaviour — reproducing it here removes a network fetch of processor_config.json
    # (absent from that repo) and the transformers-5.x incompatibility it caused.
    wave = (wave - wave.mean()) / (wave.std() + 1e-7)
    x = torch.from_numpy(wave.astype("float32")).unsqueeze(0)
    with torch.no_grad():
        out = model(x)[0].numpy().squeeze()          # (arousal, dominance, valence) in ~0..1
    a, d, v = (float(np.clip(o, 0.0, 1.0)) for o in out)
    return {"rec_arousal": round(2 * a - 1, 3),      # 0..1 -> -1..1 (ECHO axes)
            "rec_valence": round(2 * v - 1, 3),
            "rec_dominance": round(2 * d - 1, 3)}


def quadrant_of(valence: float, arousal: float) -> str:
    """Same convention as contracts.quadrant_for: v>=0 positive, a>=0 high."""
    if valence >= 0 and arousal >= 0:
        return "Q1"
    if valence < 0 and arousal >= 0:
        return "Q2"
    if valence < 0 and arousal < 0:
        return "Q3"
    return "Q4"


def _rankdata(a):
    import numpy as np
    a = np.asarray(a, dtype=float)
    order = np.argsort(a, kind="mergesort")
    ranks = np.empty(len(a), dtype=float)
    ranks[order] = np.arange(1, len(a) + 1)
    sa = a[order]
    i = 0
    while i < len(sa):
        j = i
        while j + 1 < len(sa) and sa[j + 1] == sa[i]:
            j += 1
        if j > i:
            ranks[order[i:j + 1]] = (i + 1 + j + 1) / 2.0
        i = j + 1
    return ranks


def spearman(x, y) -> float:
    import numpy as np
    x, y = np.asarray(x, float), np.asarray(y, float)
    if len(x) < 2 or len(x) != len(y):
        return float("nan")
    rx, ry = _rankdata(x), _rankdata(y)
    rx, ry = rx - rx.mean(), ry - ry.mean()
    den = np.sqrt((rx ** 2).sum() * (ry ** 2).sum())
    return float((rx * ry).sum() / den) if den > 0 else float("nan")


def _resolve_out(path: Path, force: bool) -> Path:
    if force or not path.exists():
        return path
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    cand = path.with_name(f"{path.stem}_{stamp}{path.suffix}")
    i = 1
    while cand.exists():
        cand = path.with_name(f"{path.stem}_{stamp}-{i}{path.suffix}")
        i += 1
    return cand


def _report(rows: list[dict]) -> None:
    """Per-engine accuracy + agreement, then a confusion matrix per engine.

    Engines that appear in several sessions are reported per session: in an A/B experiment only
    an engine SETTING differs (e.g. Chatterbox arousal-only vs + reference style), so both rows
    carry engine='chatterbox' and averaging by engine alone would merge the two conditions."""
    per_engine: dict[str, set] = defaultdict(set)
    for r in rows:
        per_engine[r.get("engine", "?")].add(r.get("session", ""))
    multi = {e for e, s in per_engine.items() if len(s) > 1}

    def label(r: dict) -> str:
        eng = r.get("engine", "?")
        if eng not in multi:
            return eng
        sess = (r.get("session") or "").split("_", 2)[-1]
        return f"{eng} [{sess}]" if sess else eng

    groups: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        groups[label(r)].append(r)

    print("\n== Emotion conveyance per engine (machine listener vs intended) ==")
    w = max(12, max(len(e) for e in groups) + 2)
    print(f"  {'engine':<{w}}{'quad acc':>9}{'arousal acc':>12}{'valence acc':>12}"
          f"{'rho(aro)':>10}{'rho(val)':>10}{'n':>5}")
    for eng in sorted(groups):
        g = groups[eng]
        quad_ok = mean([1.0 if r["rec_quadrant"] == r["quadrant"] else 0.0 for r in g])
        aro_ok = mean([1.0 if (float(r["rec_arousal"]) >= 0) == (float(r["arousal"]) >= 0) else 0.0 for r in g])
        val_ok = mean([1.0 if (float(r["rec_valence"]) >= 0) == (float(r["valence"]) >= 0) else 0.0 for r in g])
        r_a = spearman([float(r["arousal"]) for r in g], [float(r["rec_arousal"]) for r in g])
        r_v = spearman([float(r["valence"]) for r in g], [float(r["rec_valence"]) for r in g])
        print(f"  {eng:<{w}}{quad_ok:8.0%}{aro_ok:12.0%}{val_ok:12.0%}{r_a:10.2f}{r_v:10.2f}{len(g):5d}")
    print("  (4-class chance = 25 %; arousal/valence sign chance = 50 %)")

    quads = ["Q1", "Q2", "Q3", "Q4"]
    for eng in sorted(groups):
        print(f"\n  Confusion — {eng} (rows = intended, cols = recognised)")
        print("       " + "".join(f"{q:>6}" for q in quads))
        for qi in quads:
            row = [r for r in groups[eng] if r["quadrant"] == qi]
            counts = [sum(1 for r in row if r["rec_quadrant"] == qj) for qj in quads]
            print(f"    {qi:<5}" + "".join(f"{c:>6}" for c in counts))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--register", default="research/register.csv",
                    help="register to score (master register or a session register.csv)")
    ap.add_argument("--out", default=None,
                    help="output CSV (default: emotion.csv beside the register); never overwrites")
    ap.add_argument("--force", action="store_true", help="allow overwriting an existing --out")
    ap.add_argument("--param-set", default="rate_volume_pitch",
                    help="which param-set to score (the full dial set carries the emotion)")
    ap.add_argument("--model", default=None,
                    help="HF repo id OR a local folder with the model files (offline use)")
    args = ap.parse_args(argv)

    src = Path(args.register)
    if not src.exists():
        print(f"Register not found: {src}. Build one with build_register.py --build.")
        return 1

    rows = [r for r in csv.DictReader(open(src, encoding="utf-8"))
            if r.get("silent") != "yes"
            and (not args.param_set or r.get("param_set") in (args.param_set, "", None))]
    scored, missing = [], 0
    for r in rows:
        # backslash-normalised: registers written on Windows must still resolve on Linux/macOS
        p = Path(str(r.get("audio_path", "")).replace("\\", "/"))
        if not p.exists():
            missing += 1
            continue
        row = dict(r)
        row.update(predict_va(p, args.model))
        row["rec_quadrant"] = quadrant_of(row["rec_valence"], row["rec_arousal"])
        scored.append(row)

    if not scored:
        print(f"No clips scored from {src} ({missing} missing paths; param-set '{args.param_set}').")
        return 1

    fields = list(dict.fromkeys(list(scored[0].keys())))
    out = Path(args.out) if args.out else src.parent / "emotion.csv"
    out = _resolve_out(out, args.force)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(scored)

    print(f"Scored {len(scored)} clips ({missing} missing) -> {out}")
    _report(scored)
    print("\nNote: recognisers are much weaker on VALENCE than arousal (the documented valence "
          "gap; Wagner et al., 2023) — low valence agreement is partly the recogniser, not only ECHO.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
