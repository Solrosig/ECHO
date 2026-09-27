"""Figure 5.9 - Association of valence and arousal error with the listener-rated match.
Report file: ECHO Results D - basis of the felt match.png
Run from this folder:  python make_figure_5_9.py
"""
import numpy as np, pandas as pd
from echo_figstyle import (plt, INK, MUTE, GRID, DK, MD, LT, W, RAMP, BASE, TICK, LABEL, TITLE, SMALL)
from echo_figdata import NAME, TGT, contrasts, confusion, deltas, bridge, spearman
OUT = "ECHO Results D - basis of the felt match.png"
try:
    import statsmodels.formula.api as smf
except ImportError:
    raise SystemExit("Figure 5.9 needs statsmodels:  pip install statsmodels")


d = contrasts()
IV = ["preset_val_err", "preset_aro_err"]

# ------------------------------------------------ left panel: the mixed model
z = d.copy()
for c in IV:
    z["z_" + c] = (d[c] - d[c].mean()) / d[c].std(ddof=1)
m = smf.mixedlm("preset_match ~ z_preset_val_err + z_preset_aro_err",
                z, groups=z["participant_id"]).fit(reml=True)
b = {c: float(m.params["z_" + c]) for c in IV}
se = {c: float(m.bse["z_" + c]) for c in IV}
p = {c: float(m.pvalues["z_" + c]) for c in IV}
for c in IV:
    print(f"{c:16s} b={b[c]:+.4f}  se={se[c]:.4f}  p={p[c]:.3g}")
share = b["preset_val_err"] ** 2 / (b["preset_val_err"] ** 2 + b["preset_aro_err"] ** 2)
print(f"valence share of squared weight: {share:.3f}")

# ------------------------------- right panel: the ordering inside participants
per = []
for pid, g in d.groupby("participant_id"):
    per.append((pid,
                abs(np.corrcoef(g["preset_aro_err"], g["preset_match"])[0, 1]),
                abs(np.corrcoef(g["preset_val_err"], g["preset_match"])[0, 1])))
n_val = sum(1 for _, ra, rv in per if rv > ra)
print(f"valence stronger inside {n_val} of {len(per)} participants")

# ----------------------------------------------------------------- the figure
f, (axL, axR) = plt.subplots(1, 2, figsize=(W, 3.22), gridspec_kw={"width_ratios": [1.12, 1.0]})
f.subplots_adjust(left=0.135, right=0.985, top=0.855, bottom=0.175, wspace=0.42)

# left
labels = ["Arousal error", "Valence error"]
vals = [abs(b["preset_aro_err"]), abs(b["preset_val_err"])]
errs = [1.96 * se["preset_aro_err"], 1.96 * se["preset_val_err"]]
faces = ["#e8e8e8", "#2a2a2a"]
axL.set_axisbelow(True)
axL.xaxis.grid(True, color=GRID, lw=0.6)
axL.barh([0, 1], vals, height=0.52, color=faces, edgecolor=DK, lw=0.6, zorder=3)
axL.errorbar(vals, [0, 1], xerr=errs, fmt="none", ecolor=DK, elinewidth=1.0,
             capsize=3.0, capthick=1.0, zorder=4)
for y, v, e in zip([0, 1], vals, errs):
    axL.text(v + e + 0.035, y, f"{v:.3f}", fontsize=9.0, color=INK, va="center")
axL.set_yticks([0, 1]); axL.set_yticklabels(labels)
axL.set_xlim(0, 1.0); axL.set_ylim(-0.6, 1.6)
axL.set_xlabel("Rating points per standard deviation of axis error")
axL.set_title(f"Mixed model over {len(d)} trials", fontsize=9.7, color=MUTE, pad=6)
for s in ("top", "right"):
    axL.spines[s].set_visible(False)

# right
axR.set_axisbelow(True)
axR.yaxis.grid(True, color=GRID, lw=0.6)
for _, ra, rv in per:
    axR.plot([0, 1], [ra, rv], color="#c4c4c4", lw=0.8, zorder=2)
    axR.plot([0, 1], [ra, rv], marker="o", ls="none", ms=5.9, mfc="white",
             mec=DK, mew=1.0, zorder=3)
for x, col in ((0, 1), (1, 2)):
    mu = float(np.mean([r[col] for r in per]))
    axR.plot([x - 0.17, x + 0.17], [mu, mu], color=INK, lw=1.8, zorder=4)
axR.set_xticks([0, 1]); axR.set_xticklabels(["Arousal", "Valence"])
axR.set_xlim(-0.45, 1.45); axR.set_ylim(-0.03, 0.85)
axR.set_ylabel("|r| with the target-match rating")
axR.set_title(f"Each participant, {n_val} of {len(per)} favour valence",
              fontsize=9.7, color=MUTE, pad=6)
for s in ("top", "right"):
    axR.spines[s].set_visible(False)

out = OUT
f.savefig(out, dpi=300, facecolor="white"); plt.close(f)
print("wrote", out)
