"""Figure 5.4 - Predicted and listener-rated naturalness by configuration.
Report file: ECHO Results F3 - UTMOS against listener naturalness.png
Run from this folder:  python make_figure_5_4.py
"""
import numpy as np
from echo_figstyle import (plt, INK, MUTE, GRID, DK, W)
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

OUT = "ECHO Results F3 - UTMOS against listener naturalness.png"
B = bridge()
# ---------------- F3 : dumbbell, both measures on the same MOS scale
MK = {"Explicit prosody markup": "s", "Native rate, external pitch and level": "^",
      "Reference or style conditioning": "o", "Natural-language delivery instruction": "D"}
SH = {"Explicit prosody markup": "Explicit prosody markup",
      "Native rate, external pitch and level": "Native rate, external pitch, level",
      "Reference or style conditioning": "Reference or style conditioning",
      "Natural-language delivery instruction": "Natural-language instruction"}
S = B.sort_values("lis_preset_naturalness")
f, ax = plt.subplots(figsize=(W, 3.95)); f.subplots_adjust(left=0.195, right=0.875, top=0.80, bottom=0.135)
ax.axvline(4.057, color="#6a6a6a", lw=0.8, zorder=2)
ax.plot([3.353, 3.353], [-0.15, len(S) - 0.38], color="#6a6a6a", lw=0.8, ls=(0, (4, 3)), zorder=2)
ax.text(4.02, -0.46, "natural neutral speech, 4.057  ", fontsize=8.1, color=MUTE,
        ha="right", va="center")
ax.text(3.31, 0.50, "natural emotional\nspeech, 3.353", fontsize=8.1, color=MUTE,
        ha="right", va="center", linespacing=1.15)
for i, (_, r) in enumerate(S.iterrows()):
    a, b = r.lis_preset_naturalness, r.auto_utmos
    ax.plot([a, b], [i, i], color="#b0b0b0", lw=1.6, solid_capstyle="round", zorder=3)
    ax.plot([a], [i], marker="o", ms=7.0, mfc=DK, mec=DK, mew=1.0, zorder=4)
    ax.plot([b], [i], marker=MK[r.mechanism], ms=7.7, mfc="white", mec=DK, mew=1.1, zorder=4)
    ax.text(1.02, i, f"+{b - a:.2f}", transform=ax.get_yaxis_transform(),
            va="center", ha="left", fontsize=8.6, color=INK)
ax.set_yticks(range(len(S))); ax.set_yticklabels(S.label, fontsize=9.3)
ax.set_xlabel("Naturalness, mean opinion score")
ax.set_xlim(0.72, 4.85); ax.set_ylim(-0.62, len(S) - 0.38)
ax.text(1.02, len(S) - 0.30, "gap", transform=ax.get_yaxis_transform(),
        va="center", ha="left", fontsize=8.6, color=MUTE, style="italic")
frame(ax)
ax.plot([], [], marker="o", ms=6.8, mfc=DK, mec=DK, ls="none", label="Listener rating")
for m in ("Explicit prosody markup", "Native rate, external pitch and level",
          "Reference or style conditioning", "Natural-language delivery instruction"):
    ax.plot([], [], marker=MK[m], ms=7.0, mfc="white", mec=DK, mew=1.1, ls="none",
            label="UTMOS · " + SH[m])
ax.legend(loc="lower left", bbox_to_anchor=(-0.235, 1.005), ncol=2,
          handletextpad=0.4, columnspacing=1.2, labelspacing=0.32)
save(f, OUT)
