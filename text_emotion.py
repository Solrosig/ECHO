"""Layer 1: automatic emotion classification of the generated text.

Chapter 4 §4.5 defines a four-layer evaluation protocol. This is Layer 1, the text-side
counterpart of Layer 2 (speech, dimensional SER, `emotion_conveyance.py`); with Layer 3
(`cross_modal.py`) it closes Gap 3.

    "A pre-trained text-emotion classifier (j-hartmann/emotion-english-distilroberta-base,
     predicting Ekman's six emotions plus neutral) is applied to the LLM output; its label
     is mapped to a Russell quadrant via the same lookup used for the input."   -- §4.5

The label-to-quadrant step follows the categorical-dimensional mapping protocol: positions
come from published human norms (Warriner et al., 2013), not the author's judgement, and
the map is printed with every run for inspection. `neutral` gets no quadrant: "no emotion
detected" is not "calm", and mapping it would turn an abstention into a Q4 prediction.

The lexicon scores the same texts, measuring what word-level aggregation costs against a
trained classifier on identical material.

Usage:
    python text_emotion.py                          # reads echo.db, writes research/
    python text_emotion.py --prompt-version prompts-v2
    python text_emotion.py --model local_text_model # if the HF download is blocked
"""

from __future__ import annotations

import argparse
import csv
import sqlite3
from collections import Counter
from datetime import datetime
from pathlib import Path

from config import load_config
from contracts import Quadrant, quadrant_for
from judge import LexiconJudge, load_norms

MODEL_ID = "j-hartmann/emotion-english-distilroberta-base"

#: Ekman's six plus neutral, as emitted by the classifier.
LABELS = ("anger", "disgust", "fear", "joy", "neutral", "sadness", "surprise")

#: Fallback 1-9 positions for labels absent from the norms (e.g. no norms file).
#: Approximate and not citable; the run prints a warning when they are used.
_FALLBACK_POSITIONS = {
    "anger": (2.5, 7.2), "disgust": (2.4, 5.5), "fear": (2.8, 6.9),
    "joy": (8.2, 6.6), "sadness": (2.1, 3.5), "surprise": (7.0, 7.4),
}

FIELDS = ["turn_uuid", "ts", "target_quadrant", "reply", "clf_label", "clf_score",
          "clf_valence", "clf_arousal", "clf_quadrant", "clf_match",
          "lex_quadrant", "lex_match", "agree"]


def _rescale(x: float) -> float:
    """Warriner 1-9 -> [-1, 1]; 5 is the neutral midpoint."""
    return max(-1.0, min(1.0, (float(x) - 5.0) / 4.0))


def label_positions(norms: dict) -> tuple[dict, bool]:
    """Place each emotion label on the valence-arousal plane from published norms.

    The 'map' step of the categorical-dimensional protocol: coordinates are human ratings
    of the emotion words, not the author's assignment, so the mapping can be cited.
    `neutral` maps to None (see the module docstring). Returns (positions, grounded);
    grounded is False when any label used a fallback position.
    """
    grounded = True
    out: dict[str, tuple[float, float, Quadrant] | None] = {"neutral": None}
    for label in LABELS:
        if label == "neutral":
            continue
        raw = norms.get(label)
        if raw is None:
            raw = _FALLBACK_POSITIONS[label]
            grounded = False
        v, a = _rescale(raw[0]), _rescale(raw[1])
        out[label] = (v, a, quadrant_for(v, a))
    return out, grounded


def read_replies(db_path: str, prompt_version: str | None = None) -> list[dict]:
    """Accepted replies with their target quadrant, from the provenance log."""
    if not Path(db_path).exists():
        raise FileNotFoundError(f"no provenance database at {db_path}")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    sql = ("SELECT turn_uuid, ts, quadrant, reply, prompt_version FROM turns "
           "WHERE reply IS NOT NULL AND TRIM(reply) <> ''")
    args: list = []
    if prompt_version:
        sql += " AND prompt_version = ?"
        args.append(prompt_version)
    try:
        return [dict(r) for r in conn.execute(sql + " ORDER BY ts", args)]
    finally:
        conn.close()


#: Files besides the weights that `pipeline(model=<dir>)` needs when the model is
#: downloaded in a browser because TLS interception blocks Hugging Face.
MODEL_FILES = ("config.json", "merges.txt", "vocab.json", "tokenizer_config.json",
               "special_tokens_map.json")


def _classifier(model: str):
    """Lazy-load the classifier; on failure print why and return None instead of raising.

    The lexicon judge (peer-reviewed norms) is already a text-side instrument, so a blocked
    download degrades the run to lexicon-only rather than aborting it. TLS interception has
    blocked Hugging Face twice on this project (see the ser_model/ and cb_model/ workarounds).
    """
    try:
        from transformers import pipeline
    except Exception:
        print("NOTE: transformers not installed — running lexicon-only.\n"
              "      `pip install -r requirements-eval.txt` to enable the classifier.")
        return None
    try:
        return pipeline("text-classification", model=model, top_k=None)
    except Exception as exc:
        local = Path(model)
        missing = ([f for f in MODEL_FILES if not (local / f).exists()]
                   if local.is_dir() else list(MODEL_FILES))
        print(f"NOTE: could not load '{model}' ({type(exc).__name__}: {exc}).\n"
              "      Running lexicon-only. To enable the classifier, download these files\n"
              f"      in a BROWSER from https://huggingface.co/{MODEL_ID}/tree/main\n"
              f"      into a folder and pass --model <folder>:\n"
              f"        {', '.join(missing)}, and model.safetensors")
        return None


def classify(texts: list[str], model: str) -> list[tuple[str, float] | None]:
    """Top label and score per text; a list of None when the classifier is unavailable."""
    clf = _classifier(model)
    if clf is None:
        return [None] * len(texts)
    out: list[tuple[str, float] | None] = []
    for text in texts:
        scored = clf(text)[0]
        best = max(scored, key=lambda d: d["score"])
        out.append((best["label"].lower(), float(best["score"])))
    return out


def _resolve_out(path: Path) -> Path:
    """Never overwrite a previous run: results are evidence."""
    if not path.exists():
        return path
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return path.with_name(f"{path.stem}_{stamp}{path.suffix}")


def macro_f1(rows: list[dict], key: str) -> tuple[float, dict[str, float]]:
    """Macro-averaged F1 over the four quadrants, as Chapter 4 §4.5 requires.

    Macro so each quadrant counts equally; micro-averaging would let a quadrant the system
    produces more often dominate. Abstentions (shown as `-`, e.g. `neutral`, which is not a
    quadrant) count as false negatives for the true class and are never credited.
    Returns (macro F1, per-quadrant F1).
    """
    per: dict[str, float] = {}
    for q in (x.value for x in Quadrant):
        tp = sum(1 for r in rows if r["target_quadrant"] == q and r[key] == q)
        fp = sum(1 for r in rows if r["target_quadrant"] != q and r[key] == q)
        fn = sum(1 for r in rows if r["target_quadrant"] == q and r[key] != q)
        prec = tp / (tp + fp) if (tp + fp) else 0.0
        rec = tp / (tp + fn) if (tp + fn) else 0.0
        per[q] = 2 * prec * rec / (prec + rec) if (prec + rec) else 0.0
    return sum(per.values()) / len(per), per


def _matrix(rows: list[dict], key: str) -> None:
    """Print the confusion matrix with abstentions (`-`); accuracy alone hides the diagnosis."""
    quads = [q.value for q in Quadrant]
    counts = Counter((r["target_quadrant"], r[key] or "-") for r in rows)
    cols = quads + ["-"]
    print("        " + "".join(f"{c:>6}" for c in cols) + "     n   acc")
    for t in quads:
        n = sum(counts[(t, c)] for c in cols)
        hit = counts[(t, t)]
        cells = "".join(f"{counts[(t, c)]:>6}" for c in cols)
        acc = f"{100.0 * hit / n:5.1f}%" if n else "    -"
        print(f"  {t}   {cells}  {n:>4}  {acc}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", default="echo.db")
    ap.add_argument("--model", default=MODEL_ID, help="HF id or a local model directory")
    ap.add_argument("--norms", default="", help="Warriner CSV (defaults to ECHO_AFFECT_NORMS)")
    ap.add_argument("--prompt-version", default=None, help="e.g. prompts-v2")
    ap.add_argument("--out", default="research/text_emotion.csv")
    args = ap.parse_args(argv)

    # Resolve the norms through the config: load_norms(None) reads only ECHO_AFFECT_NORMS, so
    # a run without it silently used the 30-word placeholder (observed 2026-08-30: fallback
    # label positions, lexicon column not comparable). The config default
    # (BRM-emot-submit.csv) is the intended source.
    norms = load_norms(args.norms or load_config().affect_norms or None)
    positions, grounded = label_positions(norms)

    print("Label -> quadrant map (positions from Warriner et al., 2013):")
    for label in LABELS:
        p = positions[label]
        if p is None:
            print(f"  {label:<9} -> (none)   'no emotion detected' is not 'calm'")
        else:
            v, a, q = p
            print(f"  {label:<9} -> {q.value}   v={v:+.2f} a={a:+.2f}")
    if not grounded:
        print("  WARNING: some labels fell back to approximate positions — not citable.")

    rows_in = read_replies(args.db, args.prompt_version)
    if not rows_in:
        print("\nNo replies found. Run demo.py first.")
        return 1
    print(f"\nClassifying {len(rows_in)} replies with {args.model} ...")

    results = classify([r["reply"] for r in rows_in], args.model)
    lex = LexiconJudge(norms)

    rows: list[dict] = []
    have_clf = any(r is not None for r in results)
    for src, res in zip(rows_in, results):
        label, score = res if res is not None else ("", 0.0)
        pos = positions.get(label)
        cq = pos[2].value if pos else None
        lq = lex.judge(src["reply"])
        lq = lq.value if lq else None
        rows.append({
            "turn_uuid": src["turn_uuid"], "ts": src["ts"],
            "target_quadrant": src["quadrant"], "reply": src["reply"],
            "clf_label": label, "clf_score": round(score, 4),
            "clf_valence": round(pos[0], 3) if pos else "",
            "clf_arousal": round(pos[1], 3) if pos else "",
            "clf_quadrant": cq, "clf_match": int(cq == src["quadrant"]),
            "lex_quadrant": lq, "lex_match": int(lq == src["quadrant"]),
            "agree": int(cq is not None and cq == lq),
        })

    out = _resolve_out(Path(args.out))
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)

    n = len(rows)
    clf_acc = 100.0 * sum(r["clf_match"] for r in rows) / n
    lex_acc = 100.0 * sum(r["lex_match"] for r in rows) / n
    agree = 100.0 * sum(r["agree"] for r in rows) / n
    if have_clf:
        print(f"\n=== Layer 1: classifier ({args.model}) ===")
        _matrix(rows, "clf_quadrant")
    print("\n=== Lexicon, same texts (word-level aggregation) ===")
    _matrix(rows, "lex_quadrant")
    lex_f1, _ = macro_f1(rows, "lex_quadrant")
    if have_clf:
        clf_f1, clf_per = macro_f1(rows, "clf_quadrant")
        print("\nper-quadrant F1 (classifier): " +
              "  ".join(f"{q}={f:.2f}" for q, f in clf_per.items()))
        print(f"\nclassifier accuracy : {clf_acc:5.1f}%   macro-F1 {clf_f1:.3f}")
        print(f"lexicon accuracy    : {lex_acc:5.1f}%   macro-F1 {lex_f1:.3f}")
        print(f"difference          : {clf_acc - lex_acc:+5.1f} points "
              f"— what word-level aggregation costs on this material")
        print(f"the two agree on    : {agree:5.1f}% of replies")
    else:
        print(f"\nlexicon accuracy    : {lex_acc:5.1f}%   macro-F1 {lex_f1:.3f}")
        print("classifier          : unavailable — LEXICON-ONLY RUN.")
        print("  Layer 1 is still measured, by a different instrument than Chapter 4 "
              "§4.5 names.\n  Declare that as a deviation if this run is reported.")
    print(f"\nwritten: {out}   ({n} rows)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
