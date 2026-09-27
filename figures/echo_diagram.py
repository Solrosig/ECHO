"""Drawing helpers for the design figures of the ECHO project report (Chapters 4 and 5, Appendix E).

The design figures share one visual language with the results figures: Liberation Serif,
monochrome, rounded boxes with a light fill and a dark hairline edge, canvases 6.3 in wide
saved at 300 dpi without a tight bounding box. Coordinates are inches from the top-left
corner of the canvas, so a layout can be read directly off the page.

    from echo_diagram import canvas, box, arrow, line, dashed_box, text, note, save
"""
from echo_figstyle import plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch, Rectangle

DPI = 300
INK, TEXT, MUTE = "#1a1a1a", "#3a3a3a", "#5a5a5a"
EDGE, FILL, SHADE = "#3c3c3c", "#fafafa", "#f0f0f0"
LIFELINE = "#b8b8b8"
TITLE, BODY, SMALL, NOTE, SECTION = 10.0, 10.0, 9.0, 9.0, 11.0


def canvas(w, h):
    """A blank canvas of w x h inches; y grows downwards."""
    fig = plt.figure(figsize=(w, h))
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, w); ax.set_ylim(h, 0); ax.axis("off")
    return fig, ax


def box(ax, x, y, w, h, lines=(), fill=FILL, bold_first=False, fs=BODY, lw=1.0, r=0.05,
        color=INK, lh=1.32, align="center", pad=0.12, dy=0.0):
    """A rounded box with centred lines of text; the first line may be bold."""
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle=f"round,pad=0,rounding_size={r}",
                                linewidth=lw, edgecolor=EDGE, facecolor=fill, zorder=2))
    lines = [lines] if isinstance(lines, str) else list(lines)
    n = len(lines)
    step = fs / 72 * lh
    y0 = y + h / 2 - (n - 1) * step / 2 + dy
    for i, t in enumerate(lines):
        weight = "bold" if (bold_first and i == 0) else "normal"
        size = fs + 0.6 if (bold_first and i == 0) else fs
        if align == "left":
            ax.text(x + pad, y0 + i * step, t, ha="left", va="center", fontsize=size,
                    fontweight=weight, color=color, zorder=3)
        else:
            ax.text(x + w / 2, y0 + i * step, t, ha="center", va="center", fontsize=size,
                    fontweight=weight, color=color, zorder=3)


def dashed_box(ax, x, y, w, h, lw=1.0, color="#9a9a9a"):
    ax.add_patch(Rectangle((x, y), w, h, fill=False, edgecolor=color, linewidth=lw,
                           linestyle=(0, (3, 2)), zorder=1))


def line(ax, pts, lw=1.0, color=EDGE, ls="-", zorder=1):
    xs, ys = zip(*pts)
    ax.plot(xs, ys, color=color, lw=lw, ls=ls, solid_capstyle="butt", solid_joinstyle="miter", zorder=zorder)


def arrow(ax, x1, y1, x2, y2, lw=1.0, color=EDGE, head=8, zorder=4):
    ax.add_patch(FancyArrowPatch((x1, y1), (x2, y2), arrowstyle="-|>", mutation_scale=head,
                                 lw=lw, color=color, shrinkA=0, shrinkB=0, zorder=zorder))


def elbow_arrow(ax, pts, lw=1.0, color=EDGE, head=8):
    """A polyline whose last segment ends in an arrowhead."""
    if len(pts) > 2:
        line(ax, pts[:-1], lw=lw, color=color, zorder=1)
    (x1, y1), (x2, y2) = pts[-2], pts[-1]
    arrow(ax, x1, y1, x2, y2, lw=lw, color=color, head=head)


def text(ax, x, y, s, fs=BODY, ha="center", va="center", color=INK, **kw):
    ax.text(x, y, s, fontsize=fs, ha=ha, va=va, color=color, zorder=3, **kw)


def note(ax, x, y, s, fs=NOTE, ha="center", color=MUTE):
    ax.text(x, y, s, fontsize=fs, ha=ha, va="center", color=color, style="italic", zorder=3)


def save(fig, name):
    fig.savefig(name, dpi=DPI, facecolor="white"); plt.close(fig); print("wrote", name)
