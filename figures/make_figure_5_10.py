"""Figure 5.10 - Acoustic separation and listener arousal improvement by configuration.
Report file: ECHO Results F5 - acoustic movement against perceived arousal.png
Run from this folder:  python make_figure_5_10.py
"""
import numpy as np
from echo_figstyle import (plt, INK, GRID, DK, W)
from echo_figdata import bridge, spearman

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

OUT = "ECHO Results F5 - acoustic movement against perceived arousal.png"
B = bridge()
# ---------------- F5 : the dissociation, with placed labels
POS = [
 {"Platform engine": (0, 1, "center", "bottom"), "Kokoro": (0, 1, "center", "bottom"),
  "CosyVoice 2": (-1, 0, "right", "center"), "Chatterbox": (1, 0, "left", "center"),
  "Platform wrapper": (1, 0, "left", "center"), "StyleTTS 2": (0, 1, "center", "bottom"),
  "eSpeak NG": (0, 1, "center", "bottom"), "Parler-TTS": (-1, 0, "right", "center"),
  "ZipVoice": (1, 0, "left", "center")},
 {"Platform engine": (0, 1, "center", "bottom"), "Kokoro": (0, 1, "center", "bottom"),
  "CosyVoice 2": (-1, 0, "right", "center"), "Chatterbox": (0, 1, "center", "bottom"),
  "Platform wrapper": (-1, 0, "right", "center"), "StyleTTS 2": (0, 1, "center", "bottom"),
  "eSpeak NG": (0, 1, "center", "bottom"), "Parler-TTS": (0, 1, "center", "bottom"),
  "ZipVoice": (1, 0, "left", "center")}]
PANEL = [("aro_sep__d_f0_median_st", "F0 arousal separation (semitones)", (-0.30, 4.05)),
         ("aro_sep__d_articulation_rate", "Articulation-rate arousal separation (syll/s)", (-0.80, 3.15))]
f, axs = plt.subplots(1, 2, figsize=(W, 3.56), sharey=True)
f.subplots_adjust(left=0.105, right=0.985, top=0.895, bottom=0.145, wspace=0.075)
for k, (ax, (col, xl, xlim)) in enumerate(zip(axs, PANEL)):
    rho, p = spearman(B[col], B.lis_imp_arousal)
    ax.axhline(0, color="#c0c0c0", lw=0.6, zorder=1)
    ux = (xlim[1] - xlim[0]) * 0.028
    for _, r in B.iterrows():
        dx, dy, ha, va = POS[k][r.label]
        ax.plot([r[col]], [r.lis_imp_arousal], marker="o", ms=7.0, mfc="white", mec=DK, mew=1.1, zorder=4)
        ax.text(r[col] + dx * ux, r.lis_imp_arousal + dy * 0.0115, r.label, fontsize=8.0,
                color=INK, ha=ha, va=va, zorder=5)
    ax.set_xlabel(xl)
    ax.text(0.5, 1.018, f"Spearman $\\rho$ = {rho:+.3f},  p = {p:.3f}", transform=ax.transAxes,
            ha="center", va="bottom", fontsize=9.0, color=INK)
    ax.set_xlim(*xlim); ax.set_ylim(-0.045, 0.225)
    frame(ax, ygrid=True)
axs[0].set_ylabel("Listener arousal improvement")
save(f, OUT)
