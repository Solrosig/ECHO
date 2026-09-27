"""Figure 5.5 - Mean emotional position from matched neutral to preset renditions.
Report file: ECHO Results A - circumplex trajectory.png
Run from this folder:  python make_figure_5_5.py
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

OUT = "ECHO Results A - circumplex trajectory.png"
# =========================================================== A  circumplex
f, ax = plt.subplots(figsize=(W, 5.00)); f.subplots_adjust(left=0.105, right=0.985, top=0.965, bottom=0.085)
ax.axhline(0, color="#9a9a9a", lw=0.7, zorder=2); ax.axvline(0, color="#9a9a9a", lw=0.7, zorder=2)
for r in (0.6, 1.0):
    ax.add_patch(plt.Circle((0, 0), r, fill=False, ec="#dedede", lw=0.6, zorder=1))
ax.text(0.97, 0.035, "positive valence", fontsize=8.4, color=MUTE, ha="right")
ax.text(-0.97, 0.035, "negative valence", fontsize=8.4, color=MUTE, ha="left")
ax.text(0.035, 0.965, "high arousal", fontsize=8.4, color=MUTE, va="top", rotation=90)
ax.text(0.035, -0.965, "low arousal", fontsize=8.4, color=MUTE, va="bottom", rotation=90)
n0 = (d.neutral_val.mean(), d.neutral_aro.mean())
LP = {"happy": (0.055, 0.02, "left"), "upset": (-0.055, 0.02, "right"),
      "sad": (-0.055, -0.06, "right"), "calm": (0.055, -0.06, "left")}
for e in ORD:
    lab, tv, ta = TGT[e]; g = d[d.emotion == e]
    pv, pa = g.preset_val.mean(), g.preset_aro.mean()
    ax.plot([tv], [ta], marker="s", ms=9.4, mfc="white", mec=DK, mew=1.2, zorder=5)
    dx, dy, ha = LP[e]
    ax.text(tv + dx, ta + dy, f"{lab}\ntarget", fontsize=8.8, color=INK, ha=ha,
            va="center", linespacing=1.25, zorder=6)
    ax.plot([pv, tv], [pa, ta], color="#c4c4c4", lw=0.8, zorder=3)
    ax.add_patch(FancyArrowPatch((n0[0], n0[1]), (pv, pa), arrowstyle="-|>", mutation_scale=11,
                                 lw=1.3, color=DK, shrinkA=3.5, shrinkB=0.5, zorder=4))
    ax.plot([pv], [pa], marker="o", ms=6.2, mfc=DK, mec=DK, zorder=5)
    ax.text(pv + (0.035 if pv >= n0[0] else -0.035), pa + (0.03 if pa >= 0 else -0.03), lab,
            fontsize=8.6, color=INK, ha="left" if pv >= n0[0] else "right",
            va="bottom" if pa >= 0 else "top", zorder=6)
ax.plot([n0[0]], [n0[1]], marker="o", ms=8.2, mfc="white", mec=DK, mew=1.2, zorder=6)
ax.text(n0[0] - 0.06, n0[1] + 0.085, "matched\nneutral", fontsize=8.6, color=INK,
        ha="right", va="center", linespacing=1.25, zorder=6)
ax.set_xlabel("Rated valence"); ax.set_ylabel("Rated arousal")
ax.set_xlim(-1.06, 1.06); ax.set_ylim(-1.06, 1.06); ax.set_aspect("equal")
ax.set_xticks([-1, -0.6, 0, 0.6, 1]); ax.set_yticks([-1, -0.6, 0, 0.6, 1])
for s in ("top", "right"): ax.spines[s].set_visible(False)
ax.tick_params(length=2.5, pad=2)
save(f, OUT)
