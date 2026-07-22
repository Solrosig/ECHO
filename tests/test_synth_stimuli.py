import csv

import synth_stimuli


def test_session_folder_register_and_md(tmp_path):
    stim = tmp_path / "stim.txt"
    stim.write_text(
        "S01: The quiet meeting was moved to the other room shortly after lunch today.\n",
        encoding="utf-8",
    )
    rc = synth_stimuli.main([
        "--engine", "mock", "--param-set", "all", "--label", "smoke",
        "--stimuli", str(stim), "--sessions-root", str(tmp_path / "sessions"),
    ])
    assert rc == 0

    sessions = list((tmp_path / "sessions").glob("*_smoke"))
    assert len(sessions) == 1
    sess = sessions[0]
    assert (sess / "register.csv").exists()
    assert (sess / "SESSION.md").exists()

    rows = list(csv.DictReader(open(sess / "register.csv", encoding="utf-8")))
    # 1 stimulus x 4 quadrants x 3 param-sets
    assert len(rows) == 12
    assert {r["param_set"] for r in rows} == {"rate", "rate_volume", "rate_volume_pitch"}
    # every clip has a hash and a duration flag
    assert all(r["sha256"] for r in rows)
    assert all(r["duration_ok"] in ("yes", "no") for r in rows)
    # the ablation masks the dials: 'rate' set has neutral volume/pitch
    rate_only = [r for r in rows if r["param_set"] == "rate"]
    assert all(r["volume"] == "1.0" and r["pitch"] == "1.0" for r in rate_only)

    assert len(list(sess.rglob("*.wav"))) == 12
