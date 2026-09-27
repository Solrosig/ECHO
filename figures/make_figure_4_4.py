"""Figure 4.4 - Study entities and the keys linking evidence to its source material.
Run from this folder:  python make_figure_4_4.py
"""
from echo_diagram import (canvas, box, line, elbow_arrow, text, note, save, INK, FILL)

OUT = "ECHO Design 4.4 - study entities and joining keys.png"
fig, ax = canvas(6.3, 4.2)


def px(v):
    """The layout was measured in 300-dpi pixels."""
    return v / 300.0



def entity(x, y, w, h, title, attrs):
    box(ax, x, y, w, h, fill=FILL, r=0.04)
    text(ax, x + w / 2, y + 0.1, title, fs=10.8, fontweight="bold")
    line(ax, [(x, y + 0.2), (x + w, y + 0.2)], lw=0.9, zorder=3)
    for i, a in enumerate(attrs):
        text(ax, x + 0.1, y + 0.283 + i * 0.148, a, fs=9.6, ha="left")


def card(x, y, s):
    text(ax, px(x), px(y), s, fs=9.6)


def rel(x, y, s):
    note(ax, px(x), px(y), s, fs=9.6, color=INK)


EW, EH2, EH3, EH4 = px(502), px(197), px(195), px(280)
entity(px(15), px(38), EW, EH2, "Participant", ["id (PK)", "pseudonymous"])
entity(px(693), px(38), EW, EH2, "Session", ["id (PK)", "study version · seed"])
entity(px(1372), px(38), EW, EH2, "Allocation group", ["id (PK)", "disclosure order"])
entity(px(15), px(340), EW, EH4, "Turn", ["id (PK) · session (FK)", "emotion target · seed", "prompt · model version", "generated text · hash"])
entity(px(693), px(340), EW, EH4, "Trial", ["id (PK) · session (FK)", "item (FK) · position", "complete playback", "replays"])
entity(px(1372), px(340), EW, EH4, "Item", ["id (PK) · condition", "configuration (FK)", "audio hash (FK)"])
entity(px(693), px(725), EW, EH3, "Rating", ["valence · arousal", "naturalness · target match"])
entity(px(1372), px(725), EW, EH3, "Configuration", ["engine · settings", "reference material"])
entity(px(693), px(1025), EW, px(140), "Audio object", ["sha256 (PK) · duration"])

# relationships and their cardinalities
line(ax, [(px(517), px(145)), (px(693), px(145))]); rel(605, 110, "has"); card(545, 180, "1"); card(668, 180, "N")
line(ax, [(px(1195), px(145)), (px(1372), px(145))]); rel(1283, 110, "belongs to"); card(1220, 180, "N"); card(1348, 180, "1")
line(ax, [(px(800), px(235)), (px(800), px(290)), (px(268), px(290)), (px(268), px(340))])
rel(530, 255, "holds"); card(760, 262, "1"); card(228, 308, "N")
line(ax, [(px(944), px(235)), (px(944), px(340))]); card(905, 262, "1"); card(905, 308, "N"); rel(1088, 287, "holds")
line(ax, [(px(1195), px(490)), (px(1372), px(490))]); rel(1283, 455, "uses"); card(1220, 520, "N"); card(1348, 520, "1")
line(ax, [(px(944), px(620)), (px(944), px(725))]); card(905, 648, "1"); card(905, 693, "N"); rel(1090, 670, "yields")
line(ax, [(px(1622), px(620)), (px(1622), px(725))]); card(1580, 648, "N"); card(1580, 693, "1"); rel(1772, 670, "names")

# the two content-hash joins, drawn bold
elbow_arrow(ax, [(px(268), px(620)), (px(268), px(1097)), (px(693), px(1097))], lw=2.2, head=12)
elbow_arrow(ax, [(px(1873), px(580)), (px(1873), px(1097)), (px(1195), px(1097))], lw=2.2, head=12)
rel(485, 1055, "1 : 1 by hash"); rel(1535, 1055, "1 : 1 by hash")

note(ax, 3.15, px(1220), "Bold connectors mark the content-hash join to the audio; the turn identifier joins wording to delivery inside Turn")
save(fig, OUT)
