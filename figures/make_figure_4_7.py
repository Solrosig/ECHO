"""Figure 4.7 - Scoring tiers and ordered selection rules for the shortlist.
Run from this folder:  python make_figure_4_7.py
"""
from echo_diagram import *

OUT = "ECHO Design 4.7 - scoring tiers and selection rules.png"
fig, ax = canvas(6.3, 2.95)

text(ax, 3.15, 0.067, "Scoring", fs=11.2, fontweight="bold")
tiers = [("Tier 0", "Admission conditions", "no measurement"),
         ("Tier 1", "Automatic scorecard", "naturalness · arousal · cost"),
         ("Tier 2", "Blinded listening", "all nine configurations")]
TX, TW, TY, TH, TG = 0.107, 1.933, 0.233, 0.6, 0.143
for i, lines in enumerate(tiers):
    x = TX + i * (TW + TG)
    box(ax, x, TY, TW, TH, lines, fs=10.4, lh=1.25)
    if i < 2:
        arrow(ax, x + TW, TY + TH / 2, x + TW + TG, TY + TH / 2)
note(ax, 2.8, 0.905, "A failed admission condition excludes on technical grounds alone;")
note(ax, 2.8, 1.03, "no automatic value removes a configuration from listening")

# the listening result enters the ordered rule
t2 = TX + 2 * (TW + TG) + TW / 2
elbow_arrow(ax, [(t2, TY + TH), (t2, 1.133), (0.76, 1.133), (0.76, 1.46)])
text(ax, 3.527, 1.26, "Ranking and selection", fs=11.2, fontweight="bold")
steps = [("Step 1", "naturalness floor"), ("Step 2", "rank on emotion", "target error"),
         ("Step 3", "tie: operational cost"), ("Step 4", "tie: alphabetical order")]
SX, SW, SY, SH, SG = 0.107, 1.3, 1.46, 0.567, 0.293
for i, lines in enumerate(steps):
    x = SX + i * (SW + SG)
    box(ax, x, SY, SW, SH, lines, fill=SHADE, fs=10.4, lh=1.25)
    if i < 3:
        arrow(ax, x + SW, SY + SH / 2, x + SW + SG, SY + SH / 2)
s4 = SX + 3 * (SW + SG) + SW / 2
elbow_arrow(ax, [(s4, SY + SH), (s4, 2.233), (3.15, 2.233), (3.15, 2.383)])
box(ax, 1.74, 2.383, 2.813, 0.467, ("Shortlist of three", "enters the conversational activity"), fs=10.4)
save(fig, OUT)
