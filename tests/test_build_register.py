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


# --- the master index is never lost (added 2026-08-31) ---------------------

def test_existing_master_is_archived_before_rewrite(tmp_path):
    """`_write_master` called `open(out, "w")` unconditionally: rebuilding silently replaced
    a 300-row index with no copy taken, recoverable only because the session folders it
    derives from happened to still exist. That is luck, not design."""
    import build_register as br

    out = tmp_path / "register.csv"
    out.write_text("old,index\n1,2\n", encoding="utf-8")
    br._write_master(out, {})
    archives = list(tmp_path.glob("register_superseded-*.csv"))
    assert len(archives) == 1
    assert archives[0].read_text(encoding="utf-8") == "old,index\n1,2\n"   # byte-identical
    assert out.exists()                                                   # canonical name kept


def test_archiving_is_a_no_op_on_a_first_build(tmp_path):
    import build_register as br

    out = tmp_path / "register.csv"
    assert br._archive_existing(out) is None
    br._write_master(out, {})
    assert not list(tmp_path.glob("*superseded*"))


def test_two_rebuilds_leave_two_archives(tmp_path):
    """Every superseded index is kept, not just the most recent one."""
    import build_register as br

    out = tmp_path / "register.csv"
    out.write_text("v1\n", encoding="utf-8")
    br._write_master(out, {})
    out.write_text("v2\n", encoding="utf-8")
    br._write_master(out, {})
    assert len(list(tmp_path.glob("register_superseded-*.csv"))) == 2


def test_index_keeps_its_canonical_name(tmp_path):
    """An index is not a result. Results get timestamped names; an index must keep the path
    downstream tools default to, or every consumer silently reads a stale file."""
    import build_register as br

    out = tmp_path / "register.csv"
    out.write_text("old\n", encoding="utf-8")
    br._write_master(out, {})
    assert out.name == "register.csv"
