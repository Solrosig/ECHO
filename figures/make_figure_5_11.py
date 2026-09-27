"""Figure 5.11 - Reduction in emotion target error by configuration and emotion target.
Report file: ECHO Results C - engine by emotion target.png
Run from this folder:  python make_figure_5_11.py
"""
import numpy as np, pandas as pd
from echo_figstyle import (plt, INK, MUTE, GRID, DK, MD, LT, W, RAMP, BASE, TICK, LABEL, TITLE, SMALL)
from echo_figdata import NAME, TGT, contrasts, confusion, deltas, bridge, spearman
from matplotlib.patches import Rectangle, FancyArrowPatch
TGT = {"happy": ("Happy", 0.6, 0.6), "upset": ("Upset", -0.6, 0.6), "sad": ("Sad", -0.6, -0.6), "calm": ("Calm", 0.6, -0.6)}
ORD = ["happy", "upset", "sad", "calm"]
d = contrasts()


def save(f, n):
    f.savefig(n, dpi=300, facecolor="white"); plt.close(f); print("wrote", n)

OUT = "ECHO Results C - engine by emotion target.png"
# =========================================================== C  engine x target
P = d.pivot_table(index="engine", columns="emotion", values="imp_tot", aggfunc="mean")
P = P.reindex(columns=ORD)
P["mean"] = P.mean(axis=1)
P = P.sort_values("mean", ascending=False)
V = P.values
f, ax = plt.subplots(figsize=(W, 4.15)); f.subplots_adjust(left=0.215, right=0.985, top=0.835, bottom=0.025)
ax.imshow(np.clip(V, 0, None), cmap=RAMP, vmin=0, vmax=0.22, aspect="auto")
for i in range(V.shape[0]):
    for j in range(V.shape[1]):
        v = V[i, j]
        if v < 0:
            ax.add_patch(Rectangle((j - .5, i - .5), 1, 1, fc="white", ec="#b0b0b0", lw=0.6,
                                   hatch="////", zorder=3))
        ax.text(j, i, f"{v:+.3f}", ha="center", va="center", fontsize=9.0, zorder=4,
                color="white" if v > 0.115 else INK)
ax.add_patch(Rectangle((3.5, -.5), 1, V.shape[0], fill=False, ec=DK, lw=1.1, zorder=5))
ax.set_xticks(range(5)); ax.set_xticklabels([TGT[e][0] for e in ORD] + ["Configuration\nmean"],
                                            fontsize=9.0, linespacing=1.25)
ax.set_yticks(range(V.shape[0])); ax.set_yticklabels([NAME[e] for e in P.index], fontsize=9.0)
ax.set_xlabel("Emotion target"); ax.xaxis.set_label_position("top"); ax.xaxis.tick_top()
ax.tick_params(length=0, pad=4)
for s in ax.spines.values(): s.set_visible(False)
save(f, OUT)
