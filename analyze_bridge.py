"""
ECHO - acoustic/listener bridge.

1. Folds the v2 acoustic measures into the canonical frozen-45 register.
2. Puts inference on the acoustic deltas: per-engine arousal and valence
   separation, bootstrap CI over engines, Wilcoxon signed-rank.
3. Links the acoustic tier to the listener tier: does an engine that moves
   the acoustics further also earn a larger listener improvement?

Unit of analysis is the engine (n = 9). Clips inside an engine share a
voice and a control mechanism, so they are not independent.

Anchors
  Juslin & Laukka (2003)  arousal -> F0 level and rate; valence -> voice quality
  Eyben et al. (2016)     GeMAPS: F0 in semitones, jitter/shimmer/HNR
  Boersma (1993)          autocorrelation F0 and HNR
  de Jong & Wempe (2009)  articulation rate over phonation time
"""
import os, sys, math, numpy as np, pandas as pd
from scipy import stats

R = os.path.join(os.path.dirname(os.path.abspath(__file__)), "research")
SEED, NB = 666, 20000
HIGH, LOW = ["happy", "upset"], ["sad", "calm"]
POS, NEG = ["happy", "calm"], ["upset", "sad"]
MECH = {"espeak": "Explicit prosody markup", "sapi5xml": "Explicit prosody markup",
        "pyttsx3": "Explicit prosody markup", "kokoro": "Native rate, external pitch and level",
        "zipvoice": "Reference or style conditioning", "chatterbox": "Reference or style conditioning",
        "styletts2": "Reference or style conditioning",
        "cosyvoice2": "Natural-language delivery instruction",
        "parlertts": "Natural-language delivery instruction"}
AROUSAL_M = ["d_f0_median_st", "d_f0_sd_st", "d_f0_range_st", "d_articulation_rate",
             "d_speech_rate", "d_pause_fraction"]
VALENCE_M = ["d_hnr_db", "d_jitter_local_pct", "d_shimmer_local_pct", "d_dynamic_range_db"]


def boot(x, n=NB, seed=SEED):
    x = np.asarray(x, float); x = x[~np.isnan(x)]
    if len(x) < 2: return float(np.mean(x)) if len(x) else np.nan, np.nan, np.nan, np.nan
    rg = np.random.default_rng(seed)
    b = rg.choice(x, size=(n, len(x)), replace=True).mean(axis=1)
    p = 2 * min((b <= 0).mean(), (b >= 0).mean())
    return float(x.mean()), float(np.percentile(b, 2.5)), float(np.percentile(b, 97.5)), float(min(p, 1.0))


def boot_rho(x, y, n=NB, seed=SEED):
    x, y = np.asarray(x, float), np.asarray(y, float)
    rho, p = stats.spearmanr(x, y)
    rg = np.random.default_rng(seed); out = []
    for _ in range(n):
        i = rg.integers(0, len(x), len(x))
        if len(set(x[i])) < 3 or len(set(y[i])) < 3: continue
        r, _ = stats.spearmanr(x[i], y[i])
        if not np.isnan(r): out.append(r)
    out = np.array(out)
    return float(rho), float(p), float(np.percentile(out, 2.5)), float(np.percentile(out, 97.5))


# ---------------------------------------------------------------- 1. register
per = pd.read_csv(os.path.join(R, "acoustics_v2_per_clip.csv"))
reg = pd.read_csv(os.path.join(R, "register_frozen45_measured.csv"))
ACO = ["dur_s", "phonation_s", "pause_fraction", "n_pauses", "speech_rate", "articulation_rate",
       "n_syllables", "dynamic_range_db", "f0_median_hz", "f0_median_st", "f0_sd_st",
       "f0_range_st", "voiced_fraction", "jitter_local_pct", "shimmer_local_pct", "hnr_db"]
reg = reg.drop(columns=[c for c in ACO if c in reg.columns])
reg = reg.merge(per[["clip_id"] + ACO], on="clip_id", how="left")
assert len(reg) == 45 and reg["f0_median_st"].notna().all(), "register merge incomplete"
reg.to_csv(os.path.join(R, "register_frozen45_measured.csv"), index=False)
print(f"register_frozen45_measured.csv  ->  {len(reg)} rows x {reg.shape[1]} columns "
      f"(+{len(ACO)} acoustic)")

# ------------------------------------------------------- 2. separation per engine
d = pd.read_csv(os.path.join(R, "acoustics_v2_deltas.csv"))
MEAS = AROUSAL_M + VALENCE_M
rows = []
for eng, g in d.groupby("engine"):
    g = g.set_index("emotion")
    r = {"engine": eng, "mechanism": MECH[eng]}
    for m in MEAS:
        r[f"aro_sep__{m}"] = g.loc[HIGH, m].mean() - g.loc[LOW, m].mean()
        r[f"val_sep__{m}"] = g.loc[POS, m].mean() - g.loc[NEG, m].mean()
    r["pitch_excursion_st"] = g["d_f0_median_st"].abs().mean()
    r["rate_excursion"] = g["d_articulation_rate"].abs().mean()
    rows.append(r)
sep = pd.DataFrame(rows).sort_values("aro_sep__d_f0_median_st", ascending=False)
sep.to_csv(os.path.join(R, "acoustic_separation_by_engine.csv"), index=False)

# --------------------------------------------------------------- 3. inference
inf = []
for axis, ms in (("arousal", AROUSAL_M), ("valence", VALENCE_M)):
    pre = "aro_sep__" if axis == "arousal" else "val_sep__"
    for m in ms:
        v = sep[pre + m].values
        mu, lo, hi, pb = boot(v)
        try:
            w, pw = stats.wilcoxon(v, alternative="two-sided")
        except Exception:
            w, pw = np.nan, np.nan
        inf.append({"axis": axis, "measure": m, "n_engines": len(v), "mean_separation": mu,
                    "ci_lo": lo, "ci_hi": hi, "p_bootstrap": pb, "wilcoxon_W": w, "p_wilcoxon": pw,
                    "n_engines_positive": int((v > 0).sum())})
inf = pd.DataFrame(inf)
inf.to_csv(os.path.join(R, "acoustic_inference.csv"), index=False)

# ------------------------------------------------------------------ 4. bridge
lis = pd.read_csv(os.path.join(R, "listener_engine_means.csv"))
h3 = pd.read_csv(os.path.join(R, "h3_per_engine.csv"))[["engine", "auto_utmos", "auto_err_aro", "auto_err_val"]]
B = sep.merge(lis, on="engine").merge(h3, on="engine")
B.to_csv(os.path.join(R, "bridge_by_engine.csv"), index=False)

link = []
PAIRS = [("aro_sep__d_f0_median_st", "lis_imp_arousal"),
         ("aro_sep__d_articulation_rate", "lis_imp_arousal"),
         ("aro_sep__d_f0_range_st", "lis_imp_arousal"),
         ("val_sep__d_hnr_db", "lis_imp_valence"),
         ("val_sep__d_jitter_local_pct", "lis_imp_valence"),
         ("val_sep__d_shimmer_local_pct", "lis_imp_valence"),
         ("aro_sep__d_f0_median_st", "lis_improvement"),
         ("pitch_excursion_st", "lis_improvement"),
         ("pitch_excursion_st", "lis_preset_naturalness"),
         ("pitch_excursion_st", "auto_utmos")]
for a, b in PAIRS:
    rho, p, lo, hi = boot_rho(B[a].values, B[b].values)
    r, pr = stats.pearsonr(B[a].values, B[b].values)
    link.append({"acoustic": a, "listener": b, "spearman_rho": rho, "p_spearman": p,
                 "rho_ci_lo": lo, "rho_ci_hi": hi, "pearson_r": r, "p_pearson": pr, "n": len(B)})
link = pd.DataFrame(link)
link.to_csv(os.path.join(R, "acoustic_listener_link.csv"), index=False)

# --------------------------------------------------------------- 5. mechanism
fam = B.groupby("mechanism").agg(
    n=("engine", "size"),
    aro_sep_f0_st=("aro_sep__d_f0_median_st", "mean"),
    aro_sep_rate=("aro_sep__d_articulation_rate", "mean"),
    pitch_excursion_st=("pitch_excursion_st", "mean"),
    lis_imp_arousal=("lis_imp_arousal", "mean"),
    lis_imp_valence=("lis_imp_valence", "mean"),
    lis_naturalness=("lis_preset_naturalness", "mean"),
    utmos=("auto_utmos", "mean")).reset_index()
fam.to_csv(os.path.join(R, "acoustic_by_mechanism.csv"), index=False)

# ----------------------------------------------------------------- 6. summary
L = []
def w(s=""): L.append(s); print(s)

w("=" * 92)
w("ACOUSTIC SEPARATION BY ENGINE   (high-arousal targets minus low-arousal targets)")
w("=" * 92)
w(f"{'engine':<12}{'mechanism':<40}{'dF0 sep':>9}{'dRate sep':>11}{'|dF0| mean':>12}")
for _, r in sep.iterrows():
    w(f"{r['engine']:<12}{r['mechanism']:<40}{r['aro_sep__d_f0_median_st']:>9.2f}"
      f"{r['aro_sep__d_articulation_rate']:>11.2f}{r['pitch_excursion_st']:>12.2f}")

w(""); w("=" * 92)
w("INFERENCE OVER ENGINES   (n = 9, 20 000 bootstrap resamples, seed 666)")
w("=" * 92)
w(f"{'axis':<9}{'measure':<26}{'mean':>9}{'95% CI':>20}{'p boot':>9}{'p Wilcox':>10}{'+/9':>6}")
for _, r in inf.iterrows():
    w(f"{r['axis']:<9}{r['measure']:<26}{r['mean_separation']:>9.3f}"
      f"{'[' + format(r['ci_lo'], '.3f') + ', ' + format(r['ci_hi'], '.3f') + ']':>20}"
      f"{r['p_bootstrap']:>9.4f}{r['p_wilcoxon']:>10.4f}{int(r['n_engines_positive']):>6}")

w(""); w("=" * 92)
w("ACOUSTIC TIER versus LISTENER TIER   (Spearman over 9 engines, bootstrap CI)")
w("=" * 92)
w(f"{'acoustic':<32}{'listener':<26}{'rho':>7}{'95% CI':>20}{'p':>8}")
for _, r in link.iterrows():
    w(f"{r['acoustic']:<32}{r['listener']:<26}{r['spearman_rho']:>7.3f}"
      f"{'[' + format(r['rho_ci_lo'], '.2f') + ', ' + format(r['rho_ci_hi'], '.2f') + ']':>20}"
      f"{r['p_spearman']:>8.3f}")

w(""); w("=" * 92)
w("BY CONTROL MECHANISM")
w("=" * 92)
w(f"{'mechanism':<40}{'n':>3}{'dF0 sep':>9}{'dRate':>8}{'|dF0|':>8}{'imp aro':>9}{'nat':>7}{'UTMOS':>7}")
for _, r in fam.iterrows():
    w(f"{r['mechanism']:<40}{int(r['n']):>3}{r['aro_sep_f0_st']:>9.2f}{r['aro_sep_rate']:>8.2f}"
      f"{r['pitch_excursion_st']:>8.2f}{r['lis_imp_arousal']:>9.3f}{r['lis_naturalness']:>7.2f}"
      f"{r['utmos']:>7.2f}")

w(""); w("=" * 92)
w("PER-TARGET F0 DELTA   (mean over 9 engines; upset is the diagnostic case)")
w("=" * 92)
for e in ["happy", "upset", "sad", "calm"]:
    v = d[d.emotion == e]["d_f0_median_st"].values
    mu, lo, hi, pb = boot(v)
    w(f"  {e:<8}{mu:>8.3f}  [{lo:>6.3f}, {hi:>6.3f}]   engines raising F0: "
      f"{int((v > 0).sum())}/9   p = {pb:.4f}")

with open(os.path.join(R, "bridge_summary.txt"), "w", encoding="utf-8") as f:
    f.write("\n".join(L) + "\n")
print("\nwritten: register_frozen45_measured.csv (updated) · acoustic_separation_by_engine.csv · "
      "acoustic_inference.csv · bridge_by_engine.csv · acoustic_listener_link.csv · "
      "acoustic_by_mechanism.csv · bridge_summary.txt")
