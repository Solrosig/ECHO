"""Six greyscale figures for section 5.3 of the ECHO project report.
House style: Liberation Serif, monochrome, hairline recessive axes, canvas sized to
final placement (6.3 in text width), 300 dpi, no tight bounding box."""
import numpy as np, pandas as pd
from echo_figstyle import (plt, INK, MUTE, GRID, DK, MD, LT, W, RAMP,
                           BASE, TICK, LABEL, TITLE, SMALL)
from scipy import stats

SEED, NB = 666, 20000
NAME = {"chatterbox": "Chatterbox", "cosyvoice2": "CosyVoice 2", "espeak": "eSpeak NG",
        "kokoro": "Kokoro", "parlertts": "Parler-TTS", "pyttsx3": "Platform wrapper",
        "sapi5xml": "Platform engine", "styletts2": "StyleTTS 2", "zipvoice": "ZipVoice"}
TGT = {"happy": "Happy", "upset": "Upset", "sad": "Sad", "calm": "Calm"}


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


C = pd.read_csv("contrasts.csv")
B = pd.read_csv("bridge_by_engine.csv")
D = pd.read_csv("acoustics_v2_deltas.csv")
B["label"] = B.engine.map(NAME)

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
ax.set_xlabel("Reduction in emotion target error, preset minus matched neutral")
ax.set_xlim(-0.03, 0.18); ax.set_ylim(-0.6, len(rows) - 0.4)
frame(ax)
save(f, "F1_quadrant_improvement.png")

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
ax.set_xlabel("Reduction in axis error, preset minus matched neutral")
ax.set_xlim(-0.045, 0.20); ax.set_ylim(-0.55, len(ORD) - 0.45)
frame(ax)
from matplotlib.patches import Patch
ax.legend(handles=[Patch(facecolor=DK, edgecolor="#3a3a3a", lw=0.55, label="Arousal axis"),
                   Patch(facecolor=LT, edgecolor="#3a3a3a", lw=0.55, label="Valence axis")],
          loc="lower left", bbox_to_anchor=(0.0, 1.005), ncol=2, handlelength=1.5, columnspacing=1.6)
save(f, "F2_axis_asymmetry.png")

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
save(f, "F4_acoustic_separation.png")

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
save(f, "F6_per_target_f0.png")
print("done")

# ------------------------------------------------ F3 and F5


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
ax.text(4.02, -0.50, "natural speech anchor, 4.057  ", fontsize=8.1, color=MUTE,
        ha="right", va="center")
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
save(f, "F3_utmos_vs_listener.png")

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
    rho, p = stats.spearmanr(B[col], B.lis_imp_arousal)
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
save(f, "F5_dissociation.png")
