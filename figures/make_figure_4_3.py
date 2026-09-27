"""Figure 4.3 - Conversational data flow through all five system layers.
Run from this folder:  python make_figure_4_3.py
"""
from echo_diagram import (canvas, box, arrow, line, text, note, save, FILL, LIFELINE)

OUT = "ECHO Design 4.3 - conversational data flow.png"
fig, ax = canvas(6.3, 2.9)

parts = [("Participant",), ("Session", "service"), ("Prompt and", "speech controls"),
         ("Generation", "services"), ("Evidence", "store")]
xs = [0.067, 1.317, 2.573, 3.827, 5.08]
W, Y, H = 1.15, 0.033, 0.394
cx = [x + W / 2 for x in xs]
for x, lines in zip(xs, parts):
    box(ax, x, Y, W, H, fill=FILL)
    step = 10.4 / 72 * 1.25
    for i, t in enumerate(lines):
        text(ax, x + W / 2, Y + H / 2 - (len(lines) - 1) * step / 2 + i * step, t, fs=10.4, fontweight="bold")
for c in cx:
    line(ax, [(c, Y + H), (c, 2.567)], color=LIFELINE, lw=1.0, ls=(0, (2.5, 2.5)))

# one turn, top to bottom
flows = [(0, 1, 0.623, "emotion target and message"),
         (1, 2, 0.9, "validated control contract"),
         (2, 3, 1.173, "versioned prompt"),
         (3, 2, 1.45, "reply text"),
         (2, 3, 1.727, "engine settings from the same target"),
         (3, 1, 2.0, "audio, duration, hash, settings applied"),
         (1, 4, 2.277, "turn record: versions, seed, text, hash"),
         (4, 0, 2.493, "reply in text and in speech")]
for a, b, y, label in flows:
    arrow(ax, cx[a], y, cx[b], y, lw=1.2, head=9)
    text(ax, (cx[a] + cx[b]) / 2, y - 0.11, label, fs=9.6)

note(ax, 3.15, 2.76, "No synthesis is performed while a participant is rating; listening trials play the pre-rendered corpus")
save(fig, OUT)
