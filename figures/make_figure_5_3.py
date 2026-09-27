"""Figure 5.3 - Fundamental-frequency separation between high- and low-arousal targets.
Report file: ECHO Results F4 - F0 arousal separation by engine.png
Run from this folder:  python make_figure_5_3.py
"""
import numpy as np
from echo_figstyle import (plt, INK, GRID, LT, W)
from echo_figdata import bridge

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

OUT = "ECHO Results F4 - F0 arousal separation by engine.png"
B = bridge()
# ------------------------------------------------ F4 acoustic separation per engine
S = B.sort_values("aro_sep__d_f0_median_st")
f, ax = plt.subplots(figsize=(W, 3.39)); f.subplots_adjust(left=0.215, right=0.905, top=0.955, bottom=0.145)
yy = np.arange(len(S))
ax.barh(yy, S["aro_sep__d_f0_median_st"], height=0.6, color=LT, edgecolor="#3a3a3a", lw=0.6, zorder=3)
for i, (_, r) in enumerate(S.iterrows()):
    v = r["aro_sep__d_f0_median_st"]
    ax.text(v + 0.055, i, f"{v:+.2f}", va="center", ha="left", fontsize=8.6, color=INK)
ax.axvline(0, color="#8a8a8a", lw=0.7, zorder=4)
ax.set_yticks(yy); ax.set_yticklabels(S.label, fontsize=9.3)
ax.set_xlabel("F0 arousal separation, semitones  (high-arousal targets minus low-arousal targets)")
ax.set_xlim(0, 4.05); ax.set_ylim(-0.6, len(S) - 0.4)
frame(ax)
save(f, OUT)
