import csv

import build_register
import synth_stimuli


def _make_session(root, stim, param_set, label):
    synth_stimuli.main([
        "--engine", "mock", "--param-set", param_set, "--label", label,
        "--stimuli", str(stim), "--sessions-root", str(root),
    ])


def test_build_consolidates_and_verify(tmp_path):
    stim = tmp_path / "stim.txt"
    stim.write_text(
        "S01: The quiet meeting was moved to the other room shortly after lunch today.\n",
        encoding="utf-8",
    )
    root = tmp_path / "sessions"
    _make_session(root, stim, "rate", "a")
    _make_session(root, stim, "rate_volume", "b")

    out = tmp_path / "master.csv"
    assert build_register.main(["--build", "--sessions-root", str(root), "--out", str(out)]) == 0
    assert out.exists()

    rows = list(csv.DictReader(open(out, encoding="utf-8")))
    # 2 sessions x (1 stimulus x 4 quadrants x 1 param-set) = 8 clips
    assert len(rows) == 8
    assert all(r["source"] == "controlled" for r in rows)
    assert {r["session"] for r in rows} == {p.name for p in root.glob("*")}

    # integrity check passes on freshly written clips
    assert build_register.main(["--verify", "--sessions-root", str(root)]) == 0
