"""ZipVoice adapter (Story B4) — the CONTROLLED COMPARISON against Chatterbox Condition C.

Phase X showed that reference-clip conditioning is what finally carried emotion, but from a
single engine — so the result cannot separate the mechanism from Chatterbox. ZipVoice runs the
same mechanism on the same RAVDESS references with a different model, and these tests pin the
parts of that design that must not drift:

  * the emotion reaches the engine ONLY through the reference clip (there is no emotion dial),
  * the seed is always pinned, because flow matching is stochastic and T0.3 requires
    reproducible clips,
  * the transcript is read from the file that was actually selected, never assumed.

The model is NEVER downloaded and the subprocess is NEVER run: `_build_command` is pure, which
is exactly why the experimental parameters live there and not inside `synthesize`.
"""

from pathlib import Path

import pytest

import tts
from make_ravdess_refs import RAVDESS_STATEMENTS, statement_text
from strategies import VoiceParams


def _refs(tmp_path: Path, quadrants=("Q1", "Q2", "Q3", "Q4"), text="Kids are talking by the door."):
    for q in quadrants:
        (tmp_path / f"{q}.wav").write_bytes(b"RIFF")
        (tmp_path / f"{q}.txt").write_text(text, encoding="utf-8")
    return str(tmp_path)


def _vp(**kw):
    base = dict(voice_id="v", rate=1.0, volume=1.0, pitch=1.0, quadrant="Q1")
    base.update(kw)
    return VoiceParams(**base)


# --- speed mapping ---------------------------------------------------------

def test_speed_is_a_passthrough_of_the_rate_dial():
    """ECHO and ZipVoice share the convention (1.0 normal, >1.0 faster), so no rescaling."""
    assert tts._zipvoice_speed(1.0) == 1.0
    assert tts._zipvoice_speed(1.2) > tts._zipvoice_speed(0.8)


def test_speed_is_clamped_to_an_intelligible_band():
    assert tts._zipvoice_speed(9.0) == 2.0
    assert tts._zipvoice_speed(0.01) == 0.5


def test_speed_does_not_double_count_arousal():
    """`rate` is ALREADY the strategy's arousal-derived dial. Deriving a second speed from
    arousal would count the same signal twice and break comparability with Kokoro/eSpeak,
    which receive the same dial. Same rate + different arousal must give the same speed."""
    a = tts.ZipVoiceAdapter()._build_command(
        "hi", "r.wav", "t", tts._zipvoice_speed(_vp(rate=1.1, arousal=0.9).rate), Path("o.wav"))
    b = tts.ZipVoiceAdapter()._build_command(
        "hi", "r.wav", "t", tts._zipvoice_speed(_vp(rate=1.1, arousal=-0.9).rate), Path("o.wav"))
    assert a == b


# --- reference clip + transcript -------------------------------------------

def test_reference_returns_clip_and_transcript(tmp_path):
    a = tts.ZipVoiceAdapter(refs_dir=_refs(tmp_path))
    wav, text = a._reference_for("Q2")
    assert wav == str(tmp_path / "Q2.wav")
    assert text == "Kids are talking by the door."


def test_missing_clip_is_reported_as_absent(tmp_path):
    a = tts.ZipVoiceAdapter(refs_dir=_refs(tmp_path, quadrants=("Q1",)))
    assert a._reference_for("Q3") is None
    assert tts.ZipVoiceAdapter(refs_dir="")._reference_for("Q1") is None


def test_clip_without_transcript_is_an_error_not_a_silent_fallback(tmp_path):
    """A zero-shot engine cannot clone from audio alone. Falling back to a guessed sentence
    would condition the clone on words the clip does not contain, so this must fail loudly."""
    (tmp_path / "Q1.wav").write_bytes(b"RIFF")          # clip present, transcript absent
    a = tts.ZipVoiceAdapter(refs_dir=str(tmp_path))
    with pytest.raises(RuntimeError, match="make_ravdess_refs"):
        a._reference_for("Q1")


def test_synthesize_without_references_names_the_fix(tmp_path):
    """Unlike Chatterbox, a missing reference is fatal here — ZipVoice has no default voice."""
    a = tts.ZipVoiceAdapter(refs_dir=str(tmp_path / "nothing"))
    with pytest.raises(RuntimeError, match="no default voice"):
        a.synthesize("hello", _vp(), tmp_path / "o.wav")


# --- the command: every experimental parameter is visible here --------------

def test_seed_is_always_pinned(tmp_path):
    """T0.3: flow matching samples from noise, so an unpinned seed makes clips
    irreproducible and the provenance SHA-256 meaningless."""
    cmd = tts.ZipVoiceAdapter(refs_dir=_refs(tmp_path), seed=1234)._build_command(
        "hi", "r.wav", "t", 1.0, tmp_path / "o.wav")
    assert "--seed" in cmd and cmd[cmd.index("--seed") + 1] == "1234"


def test_command_carries_prompt_text_and_target_rms(tmp_path):
    cmd = tts.ZipVoiceAdapter(refs_dir=_refs(tmp_path), target_rms=0.0)._build_command(
        "spoken text", "ref.wav", "prompt words", 1.15, tmp_path / "o.wav")
    assert cmd[cmd.index("--prompt-wav") + 1].endswith("ref.wav")   # resolved to absolute
    assert cmd[cmd.index("--prompt-text") + 1] == "prompt words"
    assert cmd[cmd.index("--text") + 1] == "spoken text"
    assert cmd[cmd.index("--speed") + 1] == "1.15"
    # target-rms 0 disables the prompt normalisation that may erase the arousal loudness cue
    assert cmd[cmd.index("--target-rms") + 1] == "0.0"
    assert "-m" in cmd and "zipvoice.bin.infer_zipvoice" in cmd


def test_text_is_argv_not_shell(tmp_path):
    """Reply text is model output and goes straight onto the command line, so it must be
    passed as an argv list — never interpolated into a shell string."""
    cmd = tts.ZipVoiceAdapter(refs_dir=_refs(tmp_path))._build_command(
        'a "quoted" & dangerous; text', "r.wav", "t", 1.0, tmp_path / "o.wav")
    assert isinstance(cmd, list)
    assert 'a "quoted" & dangerous; text' in cmd      # intact, unescaped, one argument


def test_num_step_omitted_unless_set(tmp_path):
    refs = _refs(tmp_path)
    assert "--num-step" not in tts.ZipVoiceAdapter(refs_dir=refs, num_step=0)._build_command(
        "hi", "r.wav", "t", 1.0, tmp_path / "o.wav")
    cmd = tts.ZipVoiceAdapter(refs_dir=refs, num_step=4)._build_command(
        "hi", "r.wav", "t", 1.0, tmp_path / "o.wav")
    assert cmd[cmd.index("--num-step") + 1] == "4"


def test_incomplete_local_model_dir_is_rejected_with_the_missing_names(tmp_path):
    model = tmp_path / "zv_model"
    model.mkdir()
    (model / "model.pt").write_bytes(b"x")             # model.json + tokens.txt absent
    a = tts.ZipVoiceAdapter(refs_dir=_refs(tmp_path), model_dir=str(model))
    with pytest.raises(RuntimeError, match="tokens.txt"):
        a._build_command("hi", "r.wav", "t", 1.0, tmp_path / "o.wav")


def test_repo_goes_on_pythonpath_not_cwd(tmp_path):
    """ZipVoice ships no setup.py, so `pip install -r requirements.txt` never installs the
    package — `python -m zipvoice.bin.infer_zipvoice` only resolves from the repo root.
    PYTHONPATH is used rather than cwd because changing the working directory would
    re-base every relative path ECHO passes onto the ZipVoice checkout."""
    repo = tmp_path / "ZipVoice"
    (repo / "zipvoice").mkdir(parents=True)
    env = tts.ZipVoiceAdapter(refs_dir=_refs(tmp_path), repo=str(repo))._build_env()
    assert env is not None
    assert str(repo.resolve()) in env["PYTHONPATH"]


def test_no_repo_means_no_env_override(tmp_path):
    """Without a repo the interpreter is left to find zipvoice itself — an installed
    package must keep working."""
    assert tts.ZipVoiceAdapter(refs_dir=_refs(tmp_path))._build_env() is None


def test_existing_pythonpath_is_preserved(tmp_path):
    import os

    repo = tmp_path / "ZipVoice"
    (repo / "zipvoice").mkdir(parents=True)
    os.environ["PYTHONPATH"] = "/already/here"
    try:
        env = tts.ZipVoiceAdapter(refs_dir=_refs(tmp_path), repo=str(repo))._build_env()
    finally:
        del os.environ["PYTHONPATH"]
    assert env["PYTHONPATH"].endswith("/already/here")      # prepended, not replaced
    assert str(repo.resolve()) in env["PYTHONPATH"]


def test_repo_without_the_package_folder_is_rejected(tmp_path):
    """A path to the wrong directory must be named as such, not fail later as an
    inscrutable ModuleNotFoundError from a subprocess."""
    wrong = tmp_path / "not_the_repo"
    wrong.mkdir()
    a = tts.ZipVoiceAdapter(refs_dir=_refs(tmp_path), repo=str(wrong))
    with pytest.raises(RuntimeError, match="no 'zipvoice' folder"):
        a._build_command("hi", "r.wav", "t", 1.0, tmp_path / "o.wav")


def test_paths_are_absolute_in_the_command(tmp_path, monkeypatch):
    """The subprocess is another process with its own notion of 'here', and ECHO passes
    relative paths (refs_ravdess/Q1.wav, research/...)."""
    monkeypatch.chdir(tmp_path)
    cmd = tts.ZipVoiceAdapter(refs_dir=_refs(tmp_path))._build_command(
        "hi", "refs/Q1.wav", "t", 1.0, Path("out/o.wav"))
    assert Path(cmd[cmd.index("--prompt-wav") + 1]).is_absolute()
    assert Path(cmd[cmd.index("--res-wav-path") + 1]).is_absolute()


def test_complete_local_model_dir_is_used(tmp_path):
    model = tmp_path / "zv_model"
    model.mkdir()
    for f in tts.ZipVoiceAdapter.MODEL_FILES:
        (model / f).write_bytes(b"x")
    cmd = tts.ZipVoiceAdapter(refs_dir=_refs(tmp_path), model_dir=str(model))._build_command(
        "hi", "r.wav", "t", 1.0, tmp_path / "o.wav")
    assert cmd[cmd.index("--model-dir") + 1] == str(model)


# --- registration and declared capabilities --------------------------------

def test_output_is_converted_to_pcm16(tmp_path, monkeypatch):
    """`torchaudio.save` writes float32 WAV. Every other engine ends up 16-bit PCM, and
    `wave` (which synth_stimuli.py uses for duration) cannot read float at all — so leaving
    ZipVoice as the one float32 engine would flag every clip duration_ok=False and put a
    container difference alongside the engine difference in a comparison corpus."""
    sf = pytest.importorskip("soundfile")
    import numpy as np

    out = tmp_path / "o.wav"

    class Done:
        returncode = 0
        stderr = stdout = ""

    def fake_run(cmd, **kw):
        # stand in for the engine: write float32, as torchaudio.save does
        sf.write(str(out), np.zeros(2400, dtype="float32"), 24000, subtype="FLOAT")
        return Done()

    monkeypatch.setattr("subprocess.run", fake_run)
    a = tts.ZipVoiceAdapter(refs_dir=_refs(tmp_path))
    a.synthesize("hi", _vp(), out)
    assert sf.info(str(out)).subtype == "PCM_16"
    import wave

    with wave.open(str(out), "rb") as w:                # the reader that previously failed
        assert w.getframerate() == 24000


def test_registered_and_declared_in_capability_matrix():
    a = tts.make_tts("zipvoice", kokoro_model="x", kokoro_voices="y", zipvoice_seed=7)
    assert a.engine_id == "zipvoice" and a.native_emotion is True and a.natural is True
    assert a._seed == 7
    m = {r["engine"]: r for r in tts.capability_matrix()}
    assert m["zipvoice"]["native_emotion"] == "yes"    # emotion enters as a reference clip
    assert m["zipvoice"]["pitch"] == "no"              # no pitch dial exists on this engine
    assert m["zipvoice"]["rate"] == "yes"              # rendered natively via --speed
    # the comparison this engine exists to make: same mechanism, different model
    assert m["chatterbox"]["native_emotion"] == "yes"


def test_construction_runs_nothing():
    """No download, no subprocess, no model — the adapter must be free to construct so the
    suite stays fast and offline."""
    a = tts.ZipVoiceAdapter()
    assert a._python                                   # resolved an interpreter, nothing more
    assert a._model_name == "zipvoice"


# --- RAVDESS transcripts ---------------------------------------------------

def test_statement_text_decodes_the_filename():
    assert statement_text("03-01-03-02-01-01-01.wav") == RAVDESS_STATEMENTS["01"]
    assert statement_text("03-01-05-02-02-01-01.wav") == RAVDESS_STATEMENTS["02"]


def test_unparseable_filename_yields_no_transcript():
    """Better no transcript than the wrong one: a mismatched prompt conditions the clone on
    words the audio does not contain."""
    assert statement_text("not-a-ravdess-name.wav") is None
    assert statement_text("03-01-03-02-99-01-01.wav") is None      # unknown statement code


def test_transcript_follows_the_file_actually_selected(tmp_path):
    """find_clip() relaxes the statement constraint when an exact match is unavailable, so
    the transcript must come from the chosen file rather than from --statement."""
    import make_ravdess_refs as mrr

    src = tmp_path / "ravdess"
    src.mkdir()
    for emo in ("03", "05", "04", "02"):
        # only statement 02 exists, although the default request is statement 01
        (src / f"03-01-{emo}-02-02-01-01.wav").write_bytes(b"RIFF")
    out = tmp_path / "refs"
    assert mrr.main(["--ravdess", str(src), "--actor", "1", "--out", str(out)]) == 0
    for q in ("Q1", "Q2", "Q3", "Q4"):
        assert (out / f"{q}.wav").exists()
        assert (out / f"{q}.txt").read_text(encoding="utf-8") == RAVDESS_STATEMENTS["02"]
