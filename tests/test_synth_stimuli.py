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
    # 1 stimulus x 4 quadrants x 4 param-sets (neutral + the 3 ablation sets)
    assert len(rows) == 16
    assert {r["param_set"] for r in rows} == {"neutral", "rate", "rate_volume", "rate_volume_pitch"}
    # every clip has a hash and a duration flag
    assert all(r["sha256"] for r in rows)
    assert all(r["duration_ok"] in ("yes", "no") for r in rows)
    # the ablation masks the dials: 'rate' set has neutral volume/pitch
    rate_only = [r for r in rows if r["param_set"] == "rate"]
    assert all(r["volume"] == "1.0" and r["pitch"] == "1.0" for r in rate_only)
    # the true baseline: 'neutral' zeroes ALL dials (rate too)
    neutral = [r for r in rows if r["param_set"] == "neutral"]
    assert all(r["rate"] == "1.0" and r["volume"] == "1.0" and r["pitch"] == "1.0" for r in neutral)

    assert len(list(sess.rglob("*.wav"))) == 16


def test_neutral_param_set_is_emotionless_for_native_engines_too(tmp_path):
    """The neutral baseline must zero the EMOTION fields as well as the prosody dials, or an
    engine that conditions natively would still receive the emotion in the 'neutral' condition."""
    from contracts import EmotionContract, Quadrant
    from strategies import SymmetricStrategy

    vp = SymmetricStrategy().build_voice_params(EmotionContract.from_quadrant(Quadrant.Q1))
    assert vp.quadrant == "Q1" and vp.arousal != 0.0            # emotion present before masking

    neutral = synth_stimuli.apply_param_set(vp, "neutral")
    assert (neutral.rate, neutral.volume, neutral.pitch) == (1.0, 1.0, 1.0)
    assert neutral.valence == 0.0 and neutral.arousal == 0.0
    assert neutral.intensity == 0.0 and neutral.quadrant == ""   # no reference style either

    full = synth_stimuli.apply_param_set(vp, "rate_volume_pitch")
    assert full.quadrant == "Q1" and full.arousal != 0.0         # full set keeps the emotion


def test_second_run_same_minute_never_overwrites(tmp_path):
    """Every generated audio set must be preserved: a same-minute, same-label re-run must get
    its OWN folder (…-2), not silently overwrite the first."""
    stim = tmp_path / "stim.txt"
    stim.write_text("S01: The quiet meeting was moved to the other room today.\n", encoding="utf-8")
    root = tmp_path / "sessions"
    args = ["--engine", "mock", "--param-set", "rate", "--label", "dup",
            "--stimuli", str(stim), "--sessions-root", str(root)]
    assert synth_stimuli.main(args) == 0
    assert synth_stimuli.main(args) == 0
    sessions = sorted(p.name for p in root.glob("*dup*"))
    assert len(sessions) == 2                      # two distinct sessions, nothing clobbered
    assert any(s.endswith("-2") for s in sessions)
    for s in root.glob("*dup*"):                   # each keeps its own clips + provenance
        assert (s / "register.csv").exists() and (s / "SESSION.md").exists()
        assert len(list(s.rglob("*.wav"))) == 4
