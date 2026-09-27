"""Figure 4.5 - Deployment topology and separation of source, bundle, application and data.
Run from this folder:  python make_figure_4_5.py
"""
from echo_diagram import (canvas, box, arrow, line, text, note, save, Rectangle, EDGE, SHADE)

OUT = "ECHO Design 4.5 - deployment topology.png"
fig, ax = canvas(6.3, 2.75)

box(ax, 0.05, 0.44, 1.657, 0.51, ("Private source", "repository"), fs=10.4)
arrow(ax, 0.88, 0.95, 0.88, 1.35)
box(ax, 0.05, 1.35, 1.657, 0.5, ("Deployment bundle", "from a tagged commit"), fs=10.4)
arrow(ax, 1.707, 1.6, 1.857, 1.6)

# the running environment and its four processes
ax.add_patch(Rectangle((1.857, 0.147), 2.583, 2.18, fill=False, edgecolor=EDGE, linewidth=1.2, zorder=2))
text(ax, 3.147, 0.25, "Running application environment", fs=10.6, fontweight="bold")
for y, lines in ((0.457, ("Web application server",)),
                 (0.923, ("Speech synthesis service", "(accelerated device per call)")),
                 (1.39, ("Session service, prompt", "construction, speech controls")),
                 (1.857, ("Local language model process",))):
    box(ax, 1.943, y, 2.413, 0.403, lines, fill=SHADE, fs=10.4)

arrow(ax, 4.44, 0.91, 4.673, 0.91)
box(ax, 4.673, 0.657, 1.57, 0.51, ("Private data store", "records and audio"), fs=10.4)
line(ax, [(4.44, 1.82), (4.673, 1.82)], color="#9a9a9a", lw=1.0, ls=(0, (3, 2)))
box(ax, 4.673, 1.567, 1.57, 0.507, ("Analysis key, held", "outside every", "public artefact"), fs=10.4, lh=1.2)

note(ax, 3.15, 2.593, "Four artefacts kept apart: private repository, deployment bundle, running application, private data store")
save(fig, OUT)
