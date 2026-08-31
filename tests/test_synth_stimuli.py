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


# --- session settings record (added 2026-08-31) -----------------------------

def test_engine_settings_distinguish_conditions_of_the_same_engine():
    """Conditions in this project often differ by a SETTING, not by an engine: the two
    ZipVoice conditions of 2026-08-31 differed only in prompt normalisation and reference
    set. Until this was recorded, they were distinguishable solely by the label typed at
    the command line — so a mistyped label would silently mislabel a whole condition."""
    import synth_stimuli as ss
    from config import Config

    a = ss.engine_settings("zipvoice", Config(zipvoice_target_rms=0.1,
                                              zipvoice_refs="refs_ravdess"))
    b = ss.engine_settings("zipvoice", Config(zipvoice_target_rms=0.0,
                                              zipvoice_refs="refs_ravdess_matched"))
    assert a != b
    assert a["target_rms"] == 0.1 and b["target_rms"] == 0.0
    assert b["refs"] == "refs_ravdess_matched"
    assert "seed" in a                       # reproducibility: the seed is part of the condition


def test_engine_settings_empty_for_engines_without_any():
    import synth_stimuli as ss
    from config import Config

    assert ss.engine_settings("espeak", Config()) == {}


def test_session_md_records_the_settings(tmp_path):
    import synth_stimuli as ss

    path = tmp_path / "SESSION.md"
    ss._write_session_md(path, "purpose", "zipvoice", ["rate_volume_pitch"],
                         [("S01", "hello")], "abc123", "v0.7", 20, 5, (2.5, 15.0),
                         {"refs": "refs_ravdess_matched", "target_rms": 0.0})
    text = path.read_text(encoding="utf-8")
    assert "refs=refs_ravdess_matched" in text
    assert "target_rms=0.0" in text


def test_dotenv_is_read_but_never_overrides_a_real_variable(tmp_path, monkeypatch):
    """A settings file must not silently beat an explicit override typed for one run."""
    import config

    env = tmp_path / ".env"
    env.write_text('ECHO_TEST_FROM_FILE=file\nECHO_TEST_OVERRIDDEN="file"\n# comment\nbroken\n',
                   encoding="utf-8")
    monkeypatch.setenv("ECHO_TEST_OVERRIDDEN", "real")
    monkeypatch.delenv("ECHO_TEST_FROM_FILE", raising=False)
    config._load_dotenv(env)
    import os

    assert os.environ["ECHO_TEST_FROM_FILE"] == "file"      # supplied
    assert os.environ["ECHO_TEST_OVERRIDDEN"] == "real"     # not clobbered
    os.environ.pop("ECHO_TEST_FROM_FILE", None)


def test_missing_dotenv_is_not_an_error(tmp_path):
    """A typo in a settings file must not stop the system from starting."""
    import config

    config._load_dotenv(tmp_path / "does_not_exist.env")    # must not raise
