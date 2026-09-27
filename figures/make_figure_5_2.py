"""Figure 5.2 - Change in fundamental frequency from matched neutral renditions, by emotion target.
Report file: ECHO Results F6 - F0 change by emotion target.png
Run from this folder:  python make_figure_5_2.py
"""
import numpy as np
from echo_figstyle import (plt, INK, MUTE, GRID, DK, MD, W)
from echo_figdata import TGT, deltas

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

OUT = "ECHO Results F6 - F0 change by emotion target.png"
D = deltas()
ORD = ["happy", "sad", "upset", "calm"]
# ------------------------------------------------ F6 per-target F0 delta
f, ax = plt.subplots(figsize=(W, 2.82)); f.subplots_adjust(left=0.115, right=0.80, top=0.955, bottom=0.185)
y = np.arange(len(ORD))[::-1]
ax.axvline(0, color="#8a8a8a", lw=0.7, zorder=2)
for e, yy in zip(ORD, y):
    v = D[D.emotion == e]["d_f0_median_st"].values
    m, lo, hi = boot(v); npos = int((v > 0).sum())
    ok = (m > 0) == (e in ("happy", "upset"))
    ax.plot([lo, hi], [yy, yy], color=DK, lw=1.3, solid_capstyle="butt", zorder=3)
    for b in (lo, hi):
        ax.plot([b, b], [yy - .11, yy + .11], color=DK, lw=1.0, zorder=3)
    ax.plot(v, [yy] * len(v), marker="|", ls="none", ms=6.1, mec=MD, mew=0.8, zorder=3)
    ax.plot([m], [yy], marker="o", ms=6.8, mfc=DK if ok else "white", mec=DK, mew=1.1, zorder=4)
    ax.text(1.015, yy, f"{m:+.2f} st   {npos}/9 raise F0", transform=ax.get_yaxis_transform(),
            va="center", ha="left", fontsize=8.6, color=INK if ok else MUTE)
ax.set_yticks(y)
ax.set_yticklabels([f"{TGT[e]}\n{'high' if e in ('happy','upset') else 'low'} arousal" for e in ORD],
                   fontsize=9.0, linespacing=1.25)
ax.set_xlabel("F0 change, preset minus matched neutral (semitones)")
ax.set_xlim(-4.4, 4.1); ax.set_ylim(-0.6, len(ORD) - 0.4)
frame(ax)
save(f, OUT)
