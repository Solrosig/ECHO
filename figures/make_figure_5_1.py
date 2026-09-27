"""Figure 5.1 - Released study activities and the data each records.
Run from this folder:  python make_figure_5_1.py
"""
from echo_diagram import (canvas, box, arrow, text, save, FILL, SHADE)

OUT = "ECHO Design 5.1 - study activities.png"
fig, ax = canvas(6.3, 2.75)

cols = [("Listening", ("All forty-five frozen clips", "Ratings locked before the",
                       "emotion target is disclosed", "Breaks after fifteen and thirty")),
        ("Test", ("Five live engines on one", "fixed phrase", "Neutral and four targets", "Twenty-five messages")),
        ("Explore", ("Three live engines", "One engine per conversation", "Four emotion targets", "Twelve conversations"))]
X0, W, G = 0.05, 2.023, 0.067
for i, (title, lines) in enumerate(cols):
    x = X0 + i * (W + G)
    box(ax, x, 0.15, W, 0.383, fill=FILL)
    text(ax, x + W / 2, 0.342, title, fs=11.2, fontweight="bold")
    box(ax, x, 0.65, W, 1.2, lines, fill=SHADE, fs=10.4, lh=1.15)
    arrow(ax, x + W / 2, 1.85, x + W / 2, 2.093)
box(ax, X0, 2.093, 3 * W + 2 * G, 0.507, fill=FILL)
text(ax, 3.15, 2.347, "Every response stored with its session, item, audio hash, component versions and timestamps", fs=10.4)
save(fig, OUT)
