"""Figures A, B and C for section 5.3 — circumplex trajectory, quadrant confusion,
engine by emotion target. Same house style as the F-series."""
import numpy as np, pandas as pd
from echo_figstyle import (plt, INK, MUTE, GRID, DK, MD, LT, W, RAMP,
                           BASE, TICK, LABEL, TITLE, SMALL)
from matplotlib.patches import Rectangle, FancyArrowPatch

NAME = {"chatterbox": "Chatterbox", "cosyvoice2": "CosyVoice 2", "espeak": "eSpeak NG",
        "kokoro": "Kokoro", "parlertts": "Parler-TTS", "pyttsx3": "Platform wrapper",
        "sapi5xml": "Platform engine", "styletts2": "StyleTTS 2", "zipvoice": "ZipVoice"}
TGT = {"happy": ("Happy", 0.6, 0.6), "upset": ("Upset", -0.6, 0.6),
       "sad": ("Sad", -0.6, -0.6), "calm": ("Calm", 0.6, -0.6)}
ORD = ["happy", "upset", "sad", "calm"]
d = pd.read_csv("contrasts.csv")


def save(f, n):
    f.savefig(n, dpi=300, facecolor="white"); plt.close(f); print("wrote", n)


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
save(f, "A_circumplex_trajectory.png")

# =========================================================== B  confusion
cm = pd.read_csv("confusion_preset.csv", index_col=0)
Q = ["Q1", "Q2", "Q3", "Q4"]
QL = ["Q1\nHappy", "Q2\nUpset", "Q3\nSad", "Q4\nCalm"]
M = cm.reindex(index=Q, columns=Q).values
f, ax = plt.subplots(figsize=(W, 4.15)); f.subplots_adjust(left=0.165, right=0.985, top=0.785, bottom=0.025)
ax.imshow(M, cmap=RAMP, vmin=0, vmax=70, aspect="auto")
for i in range(4):
    for j in range(4):
        v = M[i, j]
        ax.text(j, i, f"{v:.1f}", ha="center", va="center", fontsize=10.0,
                color="white" if v > 38 else INK,
                weight="bold" if i == j else "normal")
    ax.add_patch(Rectangle((i - .5, i - .5), 1, 1, fill=False, ec=DK, lw=1.4, zorder=5))
ax.set_xticks(range(4)); ax.set_xticklabels(QL, fontsize=9.0, linespacing=1.25)
ax.set_yticks(range(4)); ax.set_yticklabels(QL, fontsize=9.0, linespacing=1.25)
ax.set_xlabel("Quadrant the listener rated"); ax.set_ylabel("Emotion target requested")
ax.xaxis.set_label_position("top"); ax.xaxis.tick_top(); ax.tick_params(length=0, pad=4)
for s in ax.spines.values(): s.set_visible(False)
save(f, "B_quadrant_confusion.png")

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
ax.set_xticks(range(5)); ax.set_xticklabels([TGT[e][0] for e in ORD] + ["Engine\nmean"],
                                            fontsize=9.0, linespacing=1.25)
ax.set_yticks(range(V.shape[0])); ax.set_yticklabels([NAME[e] for e in P.index], fontsize=9.0)
ax.set_xlabel("Emotion target"); ax.xaxis.set_label_position("top"); ax.xaxis.tick_top()
ax.tick_params(length=0, pad=4)
for s in ax.spines.values(): s.set_visible(False)
save(f, "C_engine_by_target.png")
print("done")
