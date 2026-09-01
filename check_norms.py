"""Validate an affective-norms CSV and report its COVERAGE over real text.

Story C3. The lexicon judge is only as good as the norms behind it: on 2026-08-30 it
abstained on 3 of 4 real LLM replies, and the cause was not the method but the 30-entry
placeholder table shipped inside `judge.py`. Coverage — the share of a text's words the
norms actually recognise — is the quantity that makes that failure visible in advance
instead of after a run.

Expects a Warriner-format CSV (Warriner, Kuperman & Brysbaert, 2013): a `Word` column plus
`V.Mean.Sum` and `A.Mean.Sum` on the 1-9 rating scale. Lower-case `word,valence,arousal`
headers are also accepted.

Usage:
    python check_norms.py --norms Ratings_Warriner_et_al.csv
    python check_norms.py --norms Ratings_Warriner_et_al.csv --db echo.db
    python check_norms.py --norms Ratings_Warriner_et_al.csv --text "some sentence"
"""

from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

from judge import LexiconJudge, _WORD_RE, load_norms

# Sentences with known emotional content, used when no corpus is supplied.
_FALLBACK = [
    "YESSSS! Let's shake off Monday blues and CRUSH that meeting on Thursday!",
    "That's not fair! Now I have to adjust my whole schedule for the last-minute change!",
    "Thursday already? I'm not ready for it yet.",
    "That's fine, I can adjust my schedule.",
]


def replies_from_db(db_path: str, limit: int = 200) -> list[str]:
    """Real generated replies — the only sample that reflects actual usage."""
    if not Path(db_path).exists():
        return []
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute(
            "SELECT reply FROM turns WHERE reply IS NOT NULL AND reply <> '' "
            "ORDER BY ts DESC LIMIT ?", (limit,)
        ).fetchall()
    finally:
        conn.close()
    return [r[0] for r in rows]


def validate(path: str) -> tuple[dict, list[str]]:
    """Load the norms and report structural problems rather than failing silently."""
    problems: list[str] = []
    if not Path(path).exists():
        return {}, [f"file not found: {path}"]

    norms = load_norms(path)
    if not norms:
        return {}, [f"no usable rows parsed from {path} — check the column headers"]

    # load_norms falls back to the seed table on a parse failure; catch that here rather
    # than letting a 30-word placeholder masquerade as the published norms.
    if len(norms) < 1000:
        problems.append(
            f"only {len(norms)} entries parsed — the published set has ~13,915. "
            "This is probably the built-in placeholder, not the real file."
        )

    out_of_range = [w for w, (v, a) in norms.items()
                    if not (1.0 <= v <= 9.0 and 1.0 <= a <= 9.0)]
    if out_of_range:
        problems.append(
            f"{len(out_of_range)} entries outside the 1-9 rating scale "
            f"(e.g. {out_of_range[:5]}) — is this file already rescaled?"
        )

    for probe in ("happy", "angry", "calm", "sad"):
        if probe not in norms:
            problems.append(f"expected lemma '{probe}' is absent — wrong column mapped?")

    return norms, problems


# Function words, contractions and proper nouns are deliberately absent from the Warriner
# norms, which rate CONTENT words. Counting them in the denominator understates coverage:
# a first run over real replies reported 30.8% raw coverage while the judge was in fact
# forming an opinion on 88% of texts. Raw coverage is reported for information only; the
# criterion that matters is the OPINION RATE, because that is what the gate consumes.
_FUNCTION_WORDS = {
    "a", "an", "the", "and", "or", "but", "if", "so", "of", "to", "in", "on", "at", "for",
    "with", "from", "by", "as", "is", "are", "was", "were", "be", "been", "am", "do",
    "does", "did", "have", "has", "had", "will", "would", "can", "could", "shall",
    "should", "may", "might", "must", "i", "you", "he", "she", "it", "we", "they", "me",
    "him", "her", "us", "them", "my", "your", "his", "its", "our", "their", "this",
    "that", "these", "those", "there", "here", "what", "which", "who", "when", "where",
    "how", "why", "not", "no", "yes", "all", "any", "some", "just", "now", "then", "than",
    "too", "very", "up", "down", "out", "about", "again", "still", "get", "got", "go",
}


def _is_content(word: str) -> bool:
    """Contractions and function words are not expected to be in the norms."""
    return "'" not in word and word not in _FUNCTION_WORDS


def coverage(texts: list[str], norms: dict) -> tuple[float, float, int, int, list[str]]:
    """Raw and content-word coverage, plus the most common CONTENT misses."""
    total = hits = c_total = c_hits = 0
    missed: dict[str, int] = {}
    for t in texts:
        for w in _WORD_RE.findall((t or "").lower()):
            total += 1
            found = w in norms
            hits += found
            if _is_content(w):
                c_total += 1
                c_hits += found
                if not found:
                    missed[w] = missed.get(w, 0) + 1
    pct = 100.0 * hits / total if total else 0.0
    c_pct = 100.0 * c_hits / c_total if c_total else 0.0
    top = [w for w, _ in sorted(missed.items(), key=lambda kv: -kv[1])[:15]]
    return pct, c_pct, c_hits, c_total, top


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--norms", required=True, help="path to the Warriner-format CSV")
    ap.add_argument("--db", default="echo.db", help="sample replies from this provenance DB")
    ap.add_argument("--text", action="append", help="score this text instead (repeatable)")
    args = ap.parse_args(argv)

    norms, problems = validate(args.norms)
    print(f"norms file : {args.norms}")
    print(f"entries    : {len(norms)}")
    if problems:
        print("\r\nPROBLEMS")
        for p in problems:
            print(f"  ! {p}")
    if not norms:
        return 1

    if args.text:
        texts, source = args.text, "--text"
    else:
        texts = replies_from_db(args.db)
        source = f"{args.db} ({len(texts)} replies)" if texts else "built-in samples"
        if not texts:
            texts = _FALLBACK

    pct, c_pct, c_hits, c_total, missed = coverage(texts, norms)
    print(f"\r\nsample        : {source}")
    print(f"raw coverage  : {pct:.1f}%   (all tokens — includes function words, informational only)")
    print(f"content words : {c_pct:.1f}%   ({c_hits}/{c_total} recognised)")
    if missed:
        print(f"content misses: {', '.join(missed)}")

    # The gate consumes an OPINION per text, so that is the criterion. Reported at two
    # thresholds because a one-word judgement is fragile: "yeah, that's just great" scores
    # Q1 on the single word 'great'. min_hits=2 is more robust but abstains more often.
    n = len(texts)
    rates = {}
    for min_hits in (1, 2, 3):
        judge = LexiconJudge(norms, min_hits=min_hits)
        decided = sum(1 for t in texts if judge.judge(t) is not None)
        rates[min_hits] = 100.0 * decided / n if n else 0.0
        print(f"opinions @{min_hits}+  : {decided}/{n} texts scored ({rates[min_hits]:.0f}%)")

    if len(norms) < 1000:
        print("\r\nVERDICT: placeholder table, not the published norms. Not usable.")
        return 1
    if rates[1] < 80:
        print(f"\r\nVERDICT: opinion rate {rates[1]:.0f}% is too low — the judge would abstain "
              "on too many replies and the gate would fail them. Not usable alone.")
        return 1
    print("\r\nVERDICT: usable. Set ECHO_AFFECT_NORMS to this path.")
    print(f"  Note: at min_hits=1 a single word can decide the quadrant. If robustness "
          f"matters more than\r\n  coverage, min_hits=2 costs {rates[1]-rates[2]:.0f} "
          f"percentage points of opinion rate.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
