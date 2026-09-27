"""Figure E.1 for Appendix E: the work breakdown structure as realised.

Same house style as the results figures: Liberation Serif, monochrome, rounded boxes with
a light fill, canvas 6.3 in wide at 300 dpi, no tight bounding box. Seven work packages,
four under the conversational system and three under the evaluation environment, each with
its four deliverables. Run from any folder:
    python make_figure_E_1.py
"""
from echo_figstyle import plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

DPI = 300
TEXT, MID, EDGE = "#3a3a3a", "#8a8a8a", "#3c3c3c"
FILL, FILL2 = "#f9f9f9", "#f0f0f0"
OUT = "ECHO Design E1 - work breakdown structure.png"
W, H = 6.3, 4.08  # inches

fig = plt.figure(figsize=(W, H))
ax = fig.add_axes([0, 0, 1, 1]); ax.set_xlim(0, W); ax.set_ylim(0, H); ax.axis("off")
fig.canvas.draw(); R = fig.canvas.get_renderer()

def text_w(t, fs, weight="normal"):
    tt = ax.text(0, 0, t, fontsize=fs, fontweight=weight); bb = tt.get_window_extent(R); tt.remove()
    return bb.width / fig.dpi

def fit(lines, w, fs, weight="normal"):
    while max(text_w(t, fs, weight) for t in lines) > w - 0.05 and fs > 5.5:
        fs -= 0.1
    return fs

def box(x, y, w, h, lines, fill=FILL, bold=False, fs=7.0, lw=1.0, pad=0.055, num=None):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle=f"round,pad=0,rounding_size={pad}", linewidth=lw,
                                edgecolor=EDGE, facecolor=fill, zorder=2))
    weight = "bold" if bold else "normal"
    n = len(lines); lh = fs / 72 * 1.25
    y0 = y + h / 2 + (n - 1) * lh / 2 - (0.05 if num else 0)
    for i, t in enumerate(lines):
        ax.text(x + w / 2, y0 - i * lh, t, ha="center", va="center", fontsize=fs, color=TEXT,
                fontweight=weight, zorder=3)
    if num:
        ax.text(x + 0.045, y + h - 0.045, num, ha="left", va="top", fontsize=fs - 0.6, color=MID, zorder=3)

def vline(x, y1, y2, lw=1.0): ax.plot([x, x], [y1, y2], color=EDGE, lw=lw, zorder=1, solid_capstyle="butt")
def hline(x1, x2, y, lw=1.0): ax.plot([x1, x2], [y, y], color=EDGE, lw=lw, zorder=1, solid_capstyle="butt")
def arrow_down(x, y1, y2, lw=1.0):
    ax.add_patch(FancyArrowPatch((x, y1), (x, y2), arrowstyle="-|>", mutation_scale=8, lw=lw, color=EDGE, zorder=1,
                                 shrinkA=0, shrinkB=0))

top = [("Conversational system", 0, 4), ("Evaluation environment and evidence", 4, 7)]
packages = [
    (["1  Emotion", "mapping design"],
     [("1.1", ["Quadrant", "chooser for the", "emotion target"]),
      ("1.2", ["Four emotion", "targets on the", "circumplex"]),
      ("1.3", ["Emotion control", "contract"]),
      ("1.4", ["Four control-", "mechanism", "types"])]),
    (["2  Web", "application"],
     [("2.1", ["Participant", "interface with", "three activities"]),
      ("2.2", ["Session service", "and speech", "controls"]),
      ("2.3", ["Study database", "and migrations"]),
      ("2.4", ["Hash-addressed", "audio store"])]),
    (["3  Language-model", "integration"],
     [("3.1", ["Open-weight", "model served", "locally"]),
      ("3.2", ["Fixed decoding", "and versioned", "prompt"]),
      ("3.3", ["Coherence", "check service,", "off by default"]),
      ("3.4", ["Turn record:", "versions, seed", "and hash"])]),
    (["4  Speech-engine", "integration"],
     [("4.1", ["Nine engine", "adapters under", "one contract"]),
      ("4.2", ["Four integration", "modes"]),
      ("4.3", ["Per-quadrant", "reference bank"]),
      ("4.4", ["Capability", "and coverage", "records"])]),
    (["5  Corpus and", "provenance"],
     [("5.1", ["45 frozen", "recordings,", "hash-addressed"]),
      ("5.2", ["Register linking", "value, material", "and versions"]),
      ("5.3", ["Version locks,", "hash-locked", "plan"]),
      ("5.4", ["Blinded item", "identifiers"])]),
    (["6  Measurement", "instruments"],
     [("6.1", ["Acoustic", "description of", "the signal"]),
      ("6.2", ["Predicted", "naturalness"]),
      ("6.3", ["Dimensional", "emotion", "recognition"]),
      ("6.4", ["Calibration and", "reference", "performance"])]),
    (["7  Study and", "selection"],
     [("7.1", ["Listening study", "with blinding"]),
      ("7.2", ["Fixed-phrase", "and conversa-", "tional activities"]),
      ("7.3", ["Scorecard over", "all nine", "configurations"]),
      ("7.4", ["Ordered rule", "and shortlist"])]),
]

ncol = 7; margin = 0.06; gap = 0.06
cw = (W - 2 * margin - (ncol - 1) * gap) / ncol
xs = [margin + i * (cw + gap) for i in range(ncol)]
th = 0.36; y_top = H - 0.10 - th          # top-level boxes
ph = 0.42; y_pkg = y_top - 0.34 - ph       # package boxes
lh = 0.54; lgap = 0.08; y_leaf0 = y_pkg - 0.24 - lh
spine_dx = 0.07; leaf_dx = 0.13

for label, a, b in top:
    x0 = xs[a]; x1 = xs[b - 1] + cw
    box(x0, y_top, x1 - x0, th, [label], fill=FILL2, bold=True, fs=8.4)
    xc = (x0 + x1) / 2; ybus = y_pkg + ph + 0.17
    vline(xc, y_top, ybus)
    hline(xs[a] + cw / 2, xs[b - 1] + cw / 2, ybus)
    for i in range(a, b):
        arrow_down(xs[i] + cw / 2, ybus, y_pkg + ph + 0.004)

fs_pkg = min(fit(t, cw, 7.4, "bold") for t, _ in packages)
fs_leaf = min(fit(l, cw - leaf_dx, 6.9) for _, lv in packages for _, l in lv)
for i, (title, leaves) in enumerate(packages):
    x = xs[i]
    box(x, y_pkg, cw, ph, title, fill=FILL2, bold=True, fs=fs_pkg)
    sx = x + spine_dx
    for k, (num, lines) in enumerate(leaves):
        yl = y_leaf0 - k * (lh + lgap)
        box(x + leaf_dx, yl, cw - leaf_dx, lh, lines, fill=FILL, fs=fs_leaf, num=num)
        hline(sx, x + leaf_dx, yl + lh / 2)
    vline(sx, y_pkg, y_leaf0 - 3 * (lh + lgap) + lh / 2)

fig.savefig(OUT, dpi=DPI, facecolor="white")
print("wrote", OUT)
