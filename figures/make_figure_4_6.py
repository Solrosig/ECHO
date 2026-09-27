"""Figure 4.6 - Extraction of acoustic descriptors from a frozen recording.
Run from this folder:  python make_figure_4_6.py
"""
from echo_diagram import *

OUT = "ECHO Design 4.6 - acoustic descriptor extraction.png"
fig, ax = canvas(6.3, 4.1)

box(ax, 0.11, 0.093, 6.083, 0.347, fill=FILL)
text(ax, 3.15, 0.267, "One frozen recording, identified by its content hash", fs=10.6, fontweight="bold")
note(ax, 1.557, 0.55, "Pitch path, frame by frame")
note(ax, 4.733, 0.55, "Level, timing and voice quality, whole clip")

# frame-by-frame pitch path
left = [("Frame the signal", "40 ms window · 10 ms hop"),
        ("Drop frames below 20 %", "of the peak frame energy"),
        ("Autocorrelate each frame; take the lag", "of the peak between 75 and 400 Hz"),
        ("Reject weak periodicity: peak below", "0.3 × zero-lag counts as unvoiced"),
        ("F0 of each voiced frame", "median · standard deviation · range")]
LX, LW, BH, STEP, Y0 = 0.11, 2.9, 0.433, 0.533, 0.727
arrow(ax, 0.75, 0.44, 0.75, Y0)
for i, lines in enumerate(left):
    y = Y0 + i * STEP
    box(ax, LX, y, LW, BH, lines, fill=SHADE, fs=10.4)
    if i < len(left) - 1:
        arrow(ax, LX + LW / 2, y + BH, LX + LW / 2, y + STEP)

# whole-clip descriptors fed from one spine
right = [("Root-mean-square level over", "the whole clip, in dBFS"),
         ("Fixed word count ÷ measured", "duration, in words per second"),
         ("Periodic point process", "→ jitter and shimmer, in per cent"),
         ("Harmonicity", "→ harmonics-to-noise ratio, in dB")]
RX, RW, SX = 3.283, 2.91, 3.15
arrow(ax, SX, 0.44, SX, 0.633)
line(ax, [(SX, 0.633), (SX, Y0 + 3 * STEP + BH / 2)])
for i, lines in enumerate(right):
    y = Y0 + i * STEP
    box(ax, RX, y, RW, BH, lines, fill=SHADE, fs=10.4)
    arrow(ax, SX, y + BH / 2, RX, y + BH / 2)

# one descriptor row per clip
arrow(ax, LX + LW / 2, Y0 + 4 * STEP + BH, LX + LW / 2, 3.483)
arrow(ax, RX + RW / 2, Y0 + 3 * STEP + BH, RX + RW / 2, 3.483)
box(ax, 0.11, 3.483, 6.083, 0.367, fill=FILL)
text(ax, 3.15, 3.667, "Descriptor row written beside the register entry for that hash", fs=10.6, fontweight="bold")
save(fig, OUT)
