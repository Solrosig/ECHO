"""Chatterbox adapter (Story X2) — the native-emotion-conditioning experiment.

The heavy model is never loaded here: what matters for the research claim is that the EMOTION
(not ECHO's prosody dials) is what reaches the engine, so these tests pin the emotion->native
control mapping, the per-quadrant reference selection, and the declared capabilities."""

import pytest

import tts
from contracts import EmotionContract, Quadrant
from strategies import SymmetricStrategy, VoiceParams


def test_exaggeration_tracks_arousal():
    lo, mid, hi = (tts.arousal_to_exaggeration(a) for a in (-1.0, 0.0, 1.0))
    assert lo < mid < hi                        # monotonic in arousal
    assert 0.0 <= lo and hi <= 1.0              # inside Chatterbox's valid range
    assert tts.arousal_to_exaggeration(0.6) > tts.arousal_to_exaggeration(-0.6)


def test_cfg_weight_falls_as_arousal_rises():
    """Higher exaggeration speeds speech up; a LOWER cfg_weight restores deliberate pacing."""
    assert tts.arousal_to_cfg_weight(1.0) < tts.arousal_to_cfg_weight(-1.0)
    assert all(0.0 <= tts.arousal_to_cfg_weight(a) <= 1.0 for a in (-1.0, 0.0, 1.0))


def test_voice_params_carry_the_emotion_not_only_prosody():
    """Native-conditioning engines need the emotion itself — the strategy must supply it."""
    vp = SymmetricStrategy().build_voice_params(EmotionContract.from_quadrant(Quadrant.Q2))
    assert vp.quadrant == "Q2"
    assert vp.valence < 0 and vp.arousal > 0    # Q2 = negative valence, high arousal
    assert 0.0 < vp.intensity <= 1.0


def test_reference_clip_selected_per_quadrant(tmp_path):
    (tmp_path / "Q1.wav").write_bytes(b"RIFF")          # only Q1 provided
    a = tts.ChatterboxAdapter(refs_dir=str(tmp_path))
    assert a._reference_for("Q1") == str(tmp_path / "Q1.wav")
    assert a._reference_for("Q3") is None               # missing -> no style transfer
    assert tts.ChatterboxAdapter(refs_dir="")._reference_for("Q1") is None


def test_registered_and_declared_in_capability_matrix():
    a = tts.make_tts("chatterbox", kokoro_model="x", kokoro_voices="y")
    assert a.engine_id == "chatterbox" and a.native_emotion is True and a.natural is True
    m = {r["engine"]: r for r in tts.capability_matrix()}
    assert m["chatterbox"]["native_emotion"] == "yes"
    assert m["chatterbox"]["pitch"] == "no"            # deliberately NOT external prosody
    assert m["kokoro"]["native_emotion"] == "no"       # contrast: prosody-only neural engine


def test_missing_package_raises_actionable_error(tmp_path, monkeypatch):
    """The error path must be tested WITHOUT depending on the package being absent.

    Previously this test simply called synthesize() and relied on `import chatterbox`
    failing. Once chatterbox-tts is installed in the environment the import succeeds, the
    adapter loads the real 0.5B model and begins a full neural inference — the run observed
    on 2026-08-30 took over three minutes and reported an ETA above an hour. A regression
    gate must never do that. The import is therefore forced to fail, so the branch under
    test is exercised deterministically whether or not the package is installed.
    """
    import builtins

    real_import = builtins.__import__

    def no_chatterbox(name, *args, **kwargs):
        if name == "chatterbox" or name.startswith("chatterbox."):
            raise ImportError("simulated: chatterbox-tts not installed")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", no_chatterbox)

    a = tts.ChatterboxAdapter()
    vp = VoiceParams(voice_id="v", rate=1.0, volume=1.0, pitch=1.0, quadrant="Q1")
    with pytest.raises(RuntimeError, match="chatterbox"):
        a.synthesize("hello", vp, tmp_path / "o.wav")


def test_engine_load_never_triggered_by_construction():
    """Constructing the adapter must not load the model — laziness is the guard that keeps
    the suite fast and offline."""
    a = tts.ChatterboxAdapter()
    assert a._model is None
