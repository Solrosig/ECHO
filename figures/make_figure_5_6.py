"""Figure 5.6 - Requested and listener-rated quadrants.
Report file: ECHO Results B - quadrant confusion.png
Run from this folder:  python make_figure_5_6.py
"""
from echo_figstyle import (plt, INK, DK, W, RAMP)
from echo_figdata import contrasts, confusion
from matplotlib.patches import Rectangle
TGT = {"happy": ("Happy", 0.6, 0.6), "upset": ("Upset", -0.6, 0.6), "sad": ("Sad", -0.6, -0.6), "calm": ("Calm", 0.6, -0.6)}
ORD = ["happy", "upset", "sad", "calm"]
d = contrasts()


def save(f, n):
    f.savefig(n, dpi=300, facecolor="white"); plt.close(f); print("wrote", n)

OUT = "ECHO Results B - quadrant confusion.png"
# =========================================================== B  confusion
cm = confusion()
Q = ["Q1", "Q2", "Q3", "Q4"]
QL = ["Q1\nHappy", "Q2\nUpset", "Q3\nSad", "Q4\nCalm"]
M = cm.reindex(index=Q, columns=Q).values
f, ax = plt.subplots(figsize=(W, 3.75)); f.subplots_adjust(left=0.165, right=0.985, top=0.845, bottom=0.028)
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
save(f, OUT)
