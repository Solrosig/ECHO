"""Figure 4.1 - Five-layer architecture and the path of the declared emotion target.
Run from this folder:  python make_figure_4_1.py
"""
from echo_diagram import *

OUT = "ECHO Design 4.1 - five-layer architecture.png"
fig, ax = canvas(6.3, 2.95)

layers = [("Participant interface", "Quadrant chooser · Message field · Activity pages · Ratings"),
          ("Control and orchestration", "Session service · Prompt construction · Speech controls"),
          ("Generation services", "Language model · Coherence check · Speech synthesis engines"),
          ("Evidence and provenance", "Research records · Hash-addressed audio store · Version locks"),
          ("Evaluation and selection", "Hash join · Scorecard · Declared decision rule")]
X, W, H, GAP, Y0 = 0.05, 4.22, 0.46, 0.073, 0.093
for i, (head, sub) in enumerate(layers):
    y = Y0 + i * (H + GAP)
    box(ax, X, y, W, H, fill=FILL)
    text(ax, X + 0.14, y + 0.15, head, fs=10.4, ha="left", fontweight="bold")
    text(ax, X + 0.14, y + 0.325, sub, fs=9.2, ha="left", color=TEXT)
    if i < len(layers) - 1:
        arrow(ax, X + W / 2, y + H, X + W / 2, y + H + GAP)

# the declared target, carried alongside every layer
DX, DY, DW, DH = 4.407, 0.093, 1.82, 2.574
dashed_box(ax, DX, DY, DW, DH)
text(ax, DX + DW / 2, DY + 0.08, "Declared emotion target", fs=10.8, fontweight="bold")
for y, s in ((0.893, "captured once"), (1.19, "validated at the boundary"), (1.483, "never re-derived below"),
             (1.767, "carried into every"), (1.917, "stored record")):
    text(ax, DX + DW / 2, y, s, fs=9.6)
for i in range(4):
    ym = Y0 + i * (H + GAP) + H / 2
    arrow(ax, DX, ym, X + W + 0.02, ym, color=MUTE, head=7)
ym = Y0 + 4 * (H + GAP) + H / 2
arrow(ax, X + W, ym, DX - 0.02, ym, color=MUTE, head=7)

note(ax, 0.173, 2.827, "Evaluation reads stored records only; generation is never triggered from below", ha="left")
save(fig, OUT)
