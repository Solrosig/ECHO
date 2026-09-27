"""Figure 5.7 - Reduction in emotion target error by emotion target.
Report file: ECHO Results F1 - improvement by emotion target.png
Run from this folder:  python make_figure_5_7.py
"""
import numpy as np
from echo_figstyle import (plt, INK, MUTE, GRID, DK, W)
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

OUT = "ECHO Results F1 - improvement by emotion target.png"
C = contrasts()
# ------------------------------------------------ F1 quadrant improvement
ORD = ["happy", "sad", "upset", "calm"]
rows = []
for e in ORD:
    pm = C[C.emotion == e].groupby("participant_id")["imp_tot"].mean().values
    m, lo, hi = boot(pm); rows.append((TGT[e], m, lo, hi))
f, ax = plt.subplots(figsize=(W, 2.82)); f.subplots_adjust(left=0.135, right=0.725, top=0.955, bottom=0.185)
y = np.arange(len(rows))[::-1]
ax.axvline(0, color="#8a8a8a", lw=0.7, zorder=1)
for (lab, m, lo, hi), yy in zip(rows, y):
    ax.plot([lo, hi], [yy, yy], color=DK, lw=1.3, solid_capstyle="butt", zorder=3)
    ax.plot([lo, lo], [yy - .11, yy + .11], color=DK, lw=1.0, zorder=3)
    ax.plot([hi, hi], [yy - .11, yy + .11], color=DK, lw=1.0, zorder=3)
    sig = lo > 0
    ax.plot([m], [yy], marker="o", ms=6.8, mfc=DK if sig else "white", mec=DK, mew=1.1, zorder=4)
    ax.text(1.02, yy, f"{m:+.3f}  [{lo:+.3f}, {hi:+.3f}]", transform=ax.get_yaxis_transform(),
            va="center", ha="left", fontsize=8.6, color=INK if sig else MUTE)
ax.set_yticks(y); ax.set_yticklabels([r[0] for r in rows], fontsize=9.7)
ax.set_xlabel("Reduction in emotion target error (matched neutral minus preset)")
ax.set_xlim(-0.03, 0.18); ax.set_ylim(-0.6, len(rows) - 0.4)
frame(ax)
save(f, OUT)
