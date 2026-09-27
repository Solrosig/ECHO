"""Figure 5.8 - Reduction in arousal and valence error by emotion target.
Report file: ECHO Results F2 - axis asymmetry by emotion target.png
Run from this folder:  python make_figure_5_8.py
"""
import numpy as np
from echo_figstyle import (plt, INK, GRID, DK, LT, W)
from echo_figdata import TGT, contrasts

SEED, NB = 666, 20000


def boot(x, n=NB, seed=SEED):
    x = np.asarray(x, float); rg = np.random.default_rng(seed)
    b = rg.choice(x, size=(n, len(x)), replace=True).mean(axis=1)
    return x.mean(), np.percentile(b, 2.5), np.percentile(b, 97.5)


def frame(ax, xgrid=True, ygrid=False):
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color("#8a8a8a"); ax.spines[s].set_linewidth(0.6)
    if xgrid: ax.xaxis.grid(True, color=GRID, lw=0.5, zorder=0)
    if ygrid: ax.yaxis.grid(True, color=GRID, lw=0.5, zorder=0)
    ax.set_axisbelow(True); ax.tick_params(length=2.5, pad=2)


def save(f, name):
    f.savefig(name, dpi=300, facecolor="white"); plt.close(f); print("wrote", name)

OUT = "ECHO Results F2 - axis asymmetry by emotion target.png"
C = contrasts()
ORD = ["happy", "sad", "upset", "calm"]
# ------------------------------------------------ F2 axis asymmetry
f, ax = plt.subplots(figsize=(W, 3.05)); f.subplots_adjust(left=0.135, right=0.975, top=0.87, bottom=0.175)
h = 0.34
for i, e in enumerate(ORD):
    g = C[C.emotion == e].groupby("participant_id")[["imp_aro", "imp_val"]].mean()
    yy = len(ORD) - 1 - i
    for val, off, fc in ((g.imp_aro.mean(), +h / 2 + 0.015, DK), (g.imp_val.mean(), -h / 2 - 0.015, LT)):
        ax.barh(yy + off, val, height=h, color=fc, edgecolor="#3a3a3a", lw=0.55, zorder=3)
        ax.text(val + (0.0035 if val >= 0 else -0.0035), yy + off, f"{val:+.3f}",
                va="center", ha="left" if val >= 0 else "right", fontsize=8.4, color=INK)
ax.axvline(0, color="#8a8a8a", lw=0.7, zorder=4)
ax.set_yticks(range(len(ORD))[::-1]); ax.set_yticklabels([TGT[e] for e in ORD], fontsize=9.7)
ax.set_xlabel("Reduction in axis error (matched neutral minus preset)")
ax.set_xlim(-0.045, 0.20); ax.set_ylim(-0.55, len(ORD) - 0.45)
frame(ax)
from matplotlib.patches import Patch
ax.legend(handles=[Patch(facecolor=DK, edgecolor="#3a3a3a", lw=0.55, label="Arousal axis"),
                   Patch(facecolor=LT, edgecolor="#3a3a3a", lw=0.55, label="Valence axis")],
          loc="lower left", bbox_to_anchor=(0.0, 1.005), ncol=2, handlelength=1.5, columnspacing=1.6)
save(f, OUT)
