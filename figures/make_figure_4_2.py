"""Figure 4.2 - Four integration modes connected through a common engine adapter contract.
Run from this folder:  python make_figure_4_2.py
"""
from echo_diagram import (canvas, box, arrow, line, text, save, SHADE)

OUT = "ECHO Design 4.2 - engine adapter contract.png"
fig, ax = canvas(6.3, 2.35)

modes = [("Remote accelerated", "service"), ("In-browser", "inference runtime"),
         ("Operating-system", "speech interface"), ("Command-line", "process")]
W, GAP, Y, H = 1.523, 0.037, 0.123, 0.46
for i, lines in enumerate(modes):
    x = 0.05 + i * (W + GAP)
    box(ax, x, Y, W, H, lines, fs=10.4)
    arrow(ax, x + W / 2, Y + H, x + W / 2, 0.79)

# the contract every mode implements
box(ax, 0.05, 0.79, 6.193, 0.867, fill=SHADE, lw=1.3)
text(ax, 3.15, 0.883, "One engine adapter contract", fs=11.2, fontweight="bold")
line(ax, [(3.15, 1.067), (3.15, 1.567)], color="#c0c0c0", lw=1.0, ls=(0, (1.5, 2)), zorder=3)
for y, s in ((1.207, "Accepts"), (1.357, "emotion-target coordinates · fixed intensity"),
             (1.5, "text · voice or reference identifier · seed")):
    text(ax, 1.607, y, s, fs=9.6)
for y, s in ((1.207, "Returns"), (1.357, "audio with duration and content hash"),
             (1.5, "settings applied · engine revision · failure reason")):
    text(ax, 4.683, y, s, fs=9.6)

arrow(ax, 3.15, 1.657, 3.15, 1.843)
box(ax, 1.433, 1.843, 3.434, 0.417, ("Pipeline, unchanged when", "a configuration changes"), fs=10.4)
save(fig, OUT)
