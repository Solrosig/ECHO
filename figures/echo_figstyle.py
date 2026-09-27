"""Shared figure style for the ECHO project report.

Typography is matched to the report itself. The body text of the report is Times New Roman
at 12 pt and the caption style is 9 pt, so figure text is set in Liberation Serif, which is
metrically compatible with Times New Roman, at sizes that sit between the caption and the
body. Every canvas is built at its final placement width of 6.3 inches and saved at 300 dpi
without a tight bounding box, so one point in the figure is one point on the page.
"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap

BASE = 9.5      # annotations and value labels
TICK = 9.0      # tick labels
LABEL = 10.0    # axis labels
TITLE = 10.0    # panel titles
SMALL = 8.6     # footnotes and dense in-cell text

plt.rcParams.update({
    "font.family": "Liberation Serif", "font.size": BASE,
    "mathtext.fontset": "stix",
    "axes.edgecolor": "#8a8a8a", "axes.linewidth": 0.7,
    "xtick.color": "#3a3a3a", "ytick.color": "#3a3a3a",
    "xtick.major.width": 0.7, "ytick.major.width": 0.7,
    "xtick.labelsize": TICK, "ytick.labelsize": TICK,
    "axes.labelsize": LABEL, "axes.labelcolor": "#1a1a1a",
    "axes.titlesize": TITLE,
    "legend.fontsize": TICK, "legend.frameon": False,
    "figure.facecolor": "white", "savefig.facecolor": "white",
})

INK, MUTE, GRID = "#1a1a1a", "#5a5a5a", "#d5d5d5"
DK, MD, LT = "#3a3a3a", "#9a9a9a", "#e4e4e4"
W = 6.10   # the report text column is 6.102 in, so the canvas is placed 1:1
RAMP = LinearSegmentedColormap.from_list("gs", ["#ffffff", "#2a2a2a"])
