"""Template-driven subprocess engines: StyleTTS 2, CosyVoice 2, Parler-TTS.

These three ship as REPOSITORIES, not packages — the same class of artefact as ZipVoice,
which cost five undeclared dependencies to install on 2026-08-31. The command is therefore
a TEMPLATE in configuration: research CLIs change between commits, and hard-coding one
means a code change and a test run every time upstream moves.

No engine is ever invoked here. `build_command` is pure, which is the point of separating
it — every experimental parameter is checkable offline.
"""

from pathlib import Path

import pytest

import tts
from strategies import VoiceParams


def _vp(**kw):
    base = dict(voice_id="v", rate=1.0, volume=1.0, pitch=1.0, quadrant="Q1")
    base.update(kw)
    return VoiceParams(**base)


# --- the template ----------------------------------------------------------

def test_placeholders_are_substituted(tmp_path):
    a = tts.CosyVoice2Adapter(
        template='{python} -m x --text "{text}" --instruct "{instruction}" --out {out} --seed {seed}',
        python="PY", seed=42)
    cmd = a.build_command("hello there", _vp(quadrant="Q2"), tmp_path / "o.wav")
    assert cmd[0] == "PY"
    assert "hello there" in cmd                      # one argv element, not split
    assert tts.QUADRANT_INSTRUCTIONS["Q2"] in cmd    # ditto for the instruction sentence
    assert "42" in cmd


def test_values_with_spaces_stay_one_argument(tmp_path):
    """Reply text and instruction sentences contain spaces. If the template were split
    after substitution, every word would become a separate argument."""
    a = tts.ParlerTTSAdapter(template='{python} --text "{text}"', python="PY")
    cmd = a.build_command("a long reply with spaces", _vp(), tmp_path / "o.wav")
    assert "a long reply with spaces" in cmd
    assert len(cmd) == 3


def test_unknown_placeholder_is_left_visible_not_raised(tmp_path):
    """A template written for a future flag must degrade to a visible literal in the
    command, not an exception three layers down."""
    a = tts.CosyVoice2Adapter(template="{python} --future {not_a_field}", python="PY")
    cmd = a.build_command("hi", _vp(), tmp_path / "o.wav")
    assert "{not_a_field}" in cmd


def test_missing_template_names_the_fix(tmp_path):
    with pytest.raises(RuntimeError, match="No command template"):
        tts.StyleTTS2Adapter().build_command("hi", _vp(), tmp_path / "o.wav")


def test_paths_are_absolute(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    a = tts.CosyVoice2Adapter(template="{python} --out {out}", python="PY")
    cmd = a.build_command("hi", _vp(), Path("rel/o.wav"))
    assert Path(cmd[-1]).is_absolute()


# --- the emotional channel, per mechanism ----------------------------------

def test_instruction_engines_carry_a_sentence_not_a_label():
    """Mechanism 5 routes emotion through SEMANTICS. The instruction states valence and
    arousal both, so it cannot be read as a bare categorical label."""
    for q in ("Q1", "Q2", "Q3", "Q4"):
        s = tts.QUADRANT_INSTRUCTIONS[q]
        assert len(s.split()) >= 6 and s.endswith(".")
    assert len(set(tts.QUADRANT_INSTRUCTIONS.values())) == 4      # all distinct
    assert tts.INSTRUCTION_VERSION                                # versioned and reportable


def test_instruction_is_empty_for_the_neutral_condition():
    """param_set 'neutral' clears the quadrant; the emotional channel must go silent too,
    or the baseline would not be a baseline."""
    a = tts.CosyVoice2Adapter(template="{python} --i {instruction}", python="PY")
    assert a.emotion_fields(_vp(quadrant=""))["instruction"] == ""


def test_styletts2_selects_a_reference_per_quadrant(tmp_path):
    refs = tmp_path / "refs"
    refs.mkdir()
    (refs / "Q3.wav").write_bytes(b"RIFF")
    a = tts.StyleTTS2Adapter(template="{python} --ref {ref_wav}", python="PY",
                             refs_dir=str(refs))
    assert a.emotion_fields(_vp(quadrant="Q3"))["ref_wav"].endswith("Q3.wav")
    assert a.emotion_fields(_vp(quadrant="Q1"))["ref_wav"] == ""      # absent -> empty


# --- registration ----------------------------------------------------------

def test_all_three_registered_with_correct_mechanisms():
    m = {r["engine"]: r for r in tts.capability_matrix()}
    for e in ("styletts2", "cosyvoice2", "parlertts"):
        assert m[e]["native_emotion"] == "yes"       # emotion is input, not prosody
        assert m[e]["pitch"] == "no"
    # instruction engines expose no prosodic dial at all; StyleTTS 2 renders rate
    assert m["cosyvoice2"]["rate"] == "no" and m["parlertts"]["rate"] == "no"
    assert m["styletts2"]["rate"] == "yes"


def test_make_tts_builds_each_from_config():
    from config import Config

    cfg = Config(cosyvoice2_cmd="{python} --x", cosyvoice2_python="PY", engine_seed=7)
    a = tts.make_tts("cosyvoice2", kokoro_model="x", kokoro_voices="y", cfg=cfg)
    assert a.engine_id == "cosyvoice2" and a._seed == 7
    for alias, eid in (("st2", "styletts2"), ("parler", "parlertts"), ("cv2", "cosyvoice2")):
        assert tts.make_tts(alias, kokoro_model="x", kokoro_voices="y",
                            cfg=Config()).engine_id == eid


def test_model_dir_is_validated_by_name(tmp_path):
    class Fake(tts.SubprocessTTSAdapter):
        engine_id = "fake"
        MODEL_FILES = ("weights.pt", "config.json")

    d = tmp_path / "m"
    d.mkdir()
    (d / "weights.pt").write_bytes(b"x")
    a = Fake(template="{python}", model_dir=str(d))
    with pytest.raises(RuntimeError, match="config.json"):
        a.build_command("hi", _vp(), tmp_path / "o.wav")


def test_repo_goes_on_pythonpath(tmp_path):
    a = tts.ParlerTTSAdapter(template="{python}", repo=str(tmp_path))
    assert str(tmp_path.resolve()) in a._env()["PYTHONPATH"]
    assert tts.ParlerTTSAdapter(template="{python}")._env() is None


# --- runners: the three engines have no CLI, so ECHO ships one -------------

def test_default_templates_are_not_blank():
    """A blank template means the adapter exists but can never run. None of these three
    engines ships a CLI — all are Python APIs — so the bundled runner IS the CLI."""
    from config import Config

    cfg = Config()
    for prefix in ("styletts2", "cosyvoice2", "parlertts"):
        tmpl = getattr(cfg, prefix + "_cmd")
        assert tmpl, f"{prefix} has no default command template"
        assert f"runners/{prefix}_run.py" in tmpl
        assert "{python}" in tmpl and "{text}" in tmpl and "{out}" in tmpl


def test_every_runner_exists_and_compiles():
    import py_compile
    from pathlib import Path

    for name in ("styletts2_run.py", "cosyvoice2_run.py", "parlertts_run.py"):
        p = Path("runners") / name
        assert p.exists(), f"missing runner {p}"
        py_compile.compile(str(p), doraise=True)


def test_runners_accept_the_shared_contract():
    """Every runner takes the same arguments, so the adapter does not special-case engines."""
    import re
    from pathlib import Path

    required = {"--text", "--out", "--seed"}
    for name in ("styletts2_run.py", "cosyvoice2_run.py", "parlertts_run.py"):
        src = (Path("runners") / name).read_text(encoding="utf-8")
        args = set(re.findall(r'add_argument\("(--[a-z-]+)"', src))
        assert required <= args, f"{name} missing {required - args}"


def test_instruction_engines_can_carry_a_reference_clip(tmp_path):
    """The clip means something different here than in mechanism 3: it fixes WHO speaks so
    the instruction alone carries the emotion. CosyVoice 2 requires one."""
    refs = tmp_path / "refs"
    refs.mkdir()
    (refs / "Q2.wav").write_bytes(b"RIFF")
    a = tts.CosyVoice2Adapter(template="{python} --i {instruction} --r {ref_wav}",
                              python="PY", refs_dir=str(refs))
    f = a.emotion_fields(_vp(quadrant="Q2"))
    assert f["ref_wav"].endswith("Q2.wav")
    assert f["instruction"] == tts.QUADRANT_INSTRUCTIONS["Q2"]


def test_cosyvoice_gets_refs_from_its_own_config_key():
    """Each engine reads its OWN refs key — an earlier version read styletts2_refs for all
    of them, which would have silently pointed CosyVoice at the wrong reference set."""
    from config import Config

    cfg = Config(cosyvoice2_refs="refs_cosy", styletts2_refs="refs_style")
    assert tts.make_tts("cosyvoice2", kokoro_model="x", kokoro_voices="y",
                        cfg=cfg)._refs_dir == "refs_cosy"
    assert tts.make_tts("styletts2", kokoro_model="x", kokoro_voices="y",
                        cfg=cfg)._refs_dir == "refs_style"
    assert tts.make_tts("parlertts", kokoro_model="x", kokoro_voices="y",
                        cfg=cfg)._refs_dir == ""       # names its speaker in the description
