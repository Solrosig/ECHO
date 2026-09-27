"""H3 — agreement between the automatic instruments and blinded listeners,
on identical hash-joined audio from the frozen 45-clip corpus.

Run this AFTER naturalness.py and emotion_conveyance.py have been run over
research/register_frozen45.csv.  Nothing here touches audio: it reads the two
instrument output tables, joins them to the stored listener means on item_id,
and computes the declared agreement statistics.

    python analyse_h3.py

Inputs, all in research/ :
    naturalness_frozen45.csv        UTMOS per clip          (from naturalness.py)
    emotion_frozen45.csv            recogniser, presets     (from emotion_conveyance.py --param-set preset)
    emotion_frozen45_neutral.csv    recogniser, neutrals    (optional, --param-set neutral)
    listener_item_means.csv         45 clips x 8 raters     (stored)
    listener_engine_means.csv       9 engines               (stored)
    instrument_ceilings/20260831-203638_ceilings_n80.csv    (stored)

Outputs, written beside the inputs:
    h3_per_clip.csv        one row per clip, both tiers side by side
    h3_per_engine.csv      one row per engine, the realised scorecard
    h3_summary.txt         every statistic printed below
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

RES = Path("research")
OUT_LINES: list[str] = []

# ceilings measured on 80 RAVDESS clips (20 per quadrant, 20 actors, seed 666)
CEIL = {"quadrant": 0.412, "arousal": 0.888, "valence": 0.488,
        "utmos_natural": 4.057, "utmos_lo": 3.922, "utmos_hi": 4.191}
TARGET = {"happy": (0.6, 0.6), "upset": (-0.6, 0.6),
          "sad": (-0.6, -0.6), "calm": (0.6, -0.6)}
MECH = {"espeak": "Explicit prosody markup", "sapi5xml": "Explicit prosody markup",
        "pyttsx3": "Explicit prosody markup",
        "kokoro": "Native rate, external pitch and level",
        "zipvoice": "Reference or style conditioning",
        "chatterbox": "Reference or style conditioning",
        "styletts2": "Reference or style conditioning",
        "cosyvoice2": "Natural-language delivery instruction",
        "parlertts": "Natural-language delivery instruction"}


def say(*a):
    line = " ".join(str(x) for x in a)
    print(line)
    OUT_LINES.append(line)


def need(p: Path) -> pd.DataFrame:
    if not p.exists():
        sys.exit(f"MISSING: {p}\nRun the instrument scripts first (see the header of this file).")
    return pd.read_csv(p)


def ccc(x, y):
    """Lin's concordance correlation coefficient."""
    x, y = np.asarray(x, float), np.asarray(y, float)
    m = np.isfinite(x) & np.isfinite(y)
    x, y = x[m], y[m]
    if len(x) < 3:
        return np.nan
    sx, sy = x.var(ddof=0), y.var(ddof=0)
    cov = ((x - x.mean()) * (y - y.mean())).mean()
    return 2 * cov / (sx + sy + (x.mean() - y.mean()) ** 2)


def rho_ci(x, y, n_boot=10000, seed=666):
    """Spearman rho with a bootstrap interval over pairs."""
    x, y = np.asarray(x, float), np.asarray(y, float)
    m = np.isfinite(x) & np.isfinite(y)
    x, y = x[m], y[m]
    if len(x) < 4:
        return np.nan, np.nan, np.nan, np.nan, len(x)
    r = stats.spearmanr(x, y)
    rng = np.random.default_rng(seed)
    bs = []
    for _ in range(n_boot):
        i = rng.integers(0, len(x), len(x))
        if len(set(x[i])) > 2 and len(set(y[i])) > 2:
            bs.append(stats.spearmanr(x[i], y[i]).statistic)
    lo, hi = (np.nanpercentile(bs, [2.5, 97.5]) if bs else (np.nan, np.nan))
    return r.statistic, lo, hi, r.pvalue, len(x)


def rule(t=""):
    say("\n" + "=" * 78)
    if t:
        say(t)
        say("=" * 78)


# ---------------------------------------------------------------- load
nat = need(RES / "naturalness_frozen45.csv")
emo = need(RES / "emotion_frozen45.csv")
li = need(RES / "listener_item_means.csv")
le = need(RES / "listener_engine_means.csv")

neu_p = RES / "emotion_frozen45_neutral.csv"
emo_neu = pd.read_csv(neu_p) if neu_p.exists() else None

say(f"UTMOS rows {len(nat)} · recogniser rows (presets) {len(emo)}"
    + (f" · recogniser rows (neutrals) {len(emo_neu)}" if emo_neu is not None else "")
    + f" · listener clips {len(li)}")

if emo_neu is not None:
    emo = pd.concat([emo, emo_neu], ignore_index=True)

KEY = "clip_id"        # register_frozen45.csv carries item_id in clip_id and blind_id
for df in (nat, emo):
    if KEY not in df.columns and "blind_id" in df.columns:
        df[KEY] = df["blind_id"]

auto = nat[[KEY, "engine", "param_set", "utmos"]].merge(
    emo[[KEY, "rec_valence", "rec_arousal", "rec_quadrant"]], on=KEY, how="outer")
clip = li.merge(auto, left_on="item_id", right_on=KEY, how="left",
                suffixes=("", "_auto"))
clip["engine"] = clip["engine"].fillna(clip["engine_auto"]) if "engine_auto" in clip else clip["engine"]
clip["mechanism"] = clip.engine.map(MECH)

miss_u = clip.utmos.isna().sum()
miss_s = clip.rec_valence.isna().sum()
say(f"joined on item id — clips without UTMOS: {miss_u}/45 · without recogniser: {miss_s}/45")
if miss_u or miss_s:
    say("WARNING: coverage is incomplete; the statistics below are computed on the joined subset only.")

# target coordinates and per-axis errors, both tiers, on identical audio
clip["t_val"] = clip.emotion.map(lambda e: TARGET.get(e, (np.nan, np.nan))[0])
clip["t_aro"] = clip.emotion.map(lambda e: TARGET.get(e, (np.nan, np.nan))[1])
for tier, v, a in (("lis", "lis_valence", "lis_arousal"),
                   ("auto", "rec_valence", "rec_arousal")):
    clip[f"{tier}_err_val"] = (clip.t_val - clip[v]).abs() / 2
    clip[f"{tier}_err_aro"] = (clip.t_aro - clip[a]).abs() / 2
    clip[f"{tier}_err_tot"] = (clip[f"{tier}_err_val"] + clip[f"{tier}_err_aro"]) / 2

pres = clip[clip.condition == "preset"].copy()

# ---------------------------------------------------------------- per clip
rule("H3 PART 1 — AGREEMENT PER CLIP  (the level a screening device must get right)")
pairs = [("recogniser arousal", "rec_arousal", "listener arousal", "lis_arousal", CEIL["arousal"]),
         ("recogniser valence", "rec_valence", "listener valence", "lis_valence", CEIL["valence"]),
         ("UTMOS", "utmos", "listener naturalness", "lis_naturalness", None)]
rows = []
for nm, ca, nm2, cb, ceil in pairs:
    r, lo, hi, p, n = rho_ci(clip[ca], clip[cb])
    sign = np.mean(np.sign(clip[ca].astype(float)) == np.sign(clip[cb].astype(float))) \
        if ca != "utmos" else np.nan
    # map UTMOS 1-5 and ratings 1-5 directly; map axes already on [-1,1]
    mae = np.nanmean(np.abs(clip[ca].astype(float) - clip[cb].astype(float)))
    c = ccc(clip[ca], clip[cb])
    rows.append(dict(comparison=f"{nm} vs {nm2}", n=n, rho=r, lo=lo, hi=hi, p=p,
                     sign_agreement=sign, mae=mae, ccc=c, ceiling=ceil))
    sign_txt = "  n/a" if np.isnan(sign) else format(sign, "5.1%")
    tail = ("   ceiling " + format(ceil, ".1%")) if ceil else \
           ("   natural anchor " + format(CEIL["utmos_natural"], ".3f"))
    say(f"  {nm:20s} vs {nm2:22s} n={n:2d}  rho={r:+.3f} [{lo:+.3f},{hi:+.3f}] p={p:.4f}"
        f"  sign={sign_txt}  MAE={mae:.3f}  CCC={c:+.3f}" + tail)
per_clip_stats = pd.DataFrame(rows)

rule("QUADRANT RECOVERY ON THE FROZEN CORPUS  (presets only, read against 41.2 %)")
if pres.rec_quadrant.notna().any():
    QMAP = {"happy": "Q1", "upset": "Q2", "sad": "Q3", "calm": "Q4"}
    pres["intended_q"] = pres.emotion.map(QMAP)
    acc = (pres.rec_quadrant == pres.intended_q).mean()
    say(f"  overall recovery {acc:.1%}   (instrument ceiling on natural speech 41.2 %)")
    cm = pd.crosstab(pres.intended_q, pres.rec_quadrant)
    say("\n" + cm.to_string())
    say("\n  per quadrant, corpus vs ceiling:")
    CEIL_Q = {"Q1": 0.05, "Q2": 0.90, "Q3": 0.70, "Q4": 0.00}
    for q in ["Q1", "Q2", "Q3", "Q4"]:
        g = pres[pres.intended_q == q]
        if len(g):
            say(f"    {q}  corpus {(g.rec_quadrant == q).mean():5.1%}   ceiling {CEIL_Q[q]:5.1%}")

# ---------------------------------------------------------------- per engine
rule("H3 PART 2 — AGREEMENT PER ENGINE  (the level a ranking must get right)")
eng = pres.groupby("engine").agg(
    auto_utmos=("utmos", "mean"), auto_err_tot=("auto_err_tot", "mean"),
    auto_err_aro=("auto_err_aro", "mean"), auto_err_val=("auto_err_val", "mean"),
    lis_naturalness=("lis_naturalness", "mean"), n=("item_id", "count")).reset_index()
eng = eng.merge(le, on="engine", how="left")
eng["mechanism"] = eng.engine.map(MECH)
eng["auto_transmission"] = 1 - eng.auto_err_aro        # arousal only, per the ranking rule
say(eng[["engine", "mechanism", "n", "auto_utmos", "auto_err_aro", "auto_transmission",
         "lis_improvement", "lis_preset_error", "lis_preset_naturalness"]]
    .round(3).sort_values("lis_improvement", ascending=False).to_string(index=False))

say("")
for nm, ca, cb in [("automatic arousal transmission", "auto_transmission", "lis_improvement"),
                   ("automatic arousal transmission", "auto_transmission", "lis_preset_error"),
                   ("UTMOS", "auto_utmos", "lis_preset_naturalness"),
                   ("automatic total error", "auto_err_tot", "lis_preset_error")]:
    r, lo, hi, p, n = rho_ci(eng[ca], eng[cb])
    t = stats.kendalltau(eng[ca], eng[cb])
    say(f"  {nm:32s} vs {cb:24s} n={n}  rho={r:+.3f} [{lo:+.3f},{hi:+.3f}] p={p:.3f}"
        f"  tau={t.statistic:+.3f} p={t.pvalue:.3f}")

rule("THE SCREENING QUESTION  (would the cheap instrument have chosen the same three?)")
ra = eng.set_index("engine").auto_transmission.rank(ascending=False)
rl = eng.set_index("engine").lis_improvement.rank(ascending=False)
ranks = pd.DataFrame({"automatic_rank": ra, "listener_rank": rl}).sort_values("automatic_rank")
ranks["shift"] = ranks.listener_rank - ranks.automatic_rank
say(ranks.round(1).to_string())
ta, tl = set(ra.nsmallest(3).index), set(rl.nsmallest(3).index)
say(f"\n  automatic top three: {sorted(ta)}")
say(f"  listener  top three: {sorted(tl)}")
say(f"  overlap: {len(ta & tl)}/3")
say(f"  would have been discarded by an automatic screen: {sorted(tl - ta) or 'none'}")

# ---------------------------------------------------------------- write
pres.to_csv(RES / "h3_per_clip.csv", index=False)
eng.to_csv(RES / "h3_per_engine.csv", index=False)
per_clip_stats.to_csv(RES / "h3_agreement_stats.csv", index=False)
(RES / "h3_summary.txt").write_text("\n".join(OUT_LINES), encoding="utf-8")
rule()
say("written: research/h3_per_clip.csv · h3_per_engine.csv · h3_agreement_stats.csv · h3_summary.txt")
