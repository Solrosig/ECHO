"""Emotion conveyance (Story N5). The SER model is mocked so the pipeline — quadrant
derivation, per-engine accuracy/agreement report, non-overwrite output — is tested without
torch/transformers. Real recognition runs only where those deps + weights are available."""

import csv
import wave

import emotion_conveyance as ec


def test_quadrant_of_matches_contract_convention():
    assert ec.quadrant_of(0.6, 0.6) == "Q1"      # v+ a+
    assert ec.quadrant_of(-0.6, 0.6) == "Q2"     # v- a+
    assert ec.quadrant_of(-0.6, -0.6) == "Q3"    # v- a-
    assert ec.quadrant_of(0.6, -0.6) == "Q4"     # v+ a-
    assert ec.quadrant_of(0.0, 0.0) == "Q1"      # axes count as positive


def test_spearman_known_values():
    assert ec.spearman([1, 2, 3, 4], [2, 4, 6, 8]) == 1.0
    assert ec.spearman([1, 2, 3, 4], [8, 6, 4, 2]) == -1.0


def _wav(p):
    with wave.open(str(p), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(b"\x00\x00" * 1600)


def _register(path, rows):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["audio_path", "engine", "param_set", "quadrant",
                                          "valence", "arousal", "silent"])
        w.writeheader()
        w.writerows(rows)


def test_pipeline_scores_and_reports(tmp_path, monkeypatch, capsys):
    anchors = {"Q1": (0.6, 0.6), "Q2": (-0.6, 0.6), "Q3": (-0.6, -0.6), "Q4": (0.6, -0.6)}
    rows = []
    for q, (v, a) in anchors.items():
        p = tmp_path / f"{q}.wav"
        _wav(p)
        rows.append({"audio_path": str(p), "engine": "sapi5xml", "param_set": "rate_volume_pitch",
                     "quadrant": q, "valence": v, "arousal": a, "silent": "no"})
    reg = tmp_path / "register.csv"
    _register(reg, rows)

    # perfect recogniser: returns the intended anchors -> 100 % quadrant accuracy
    def fake(path, model_id=None):
        q = str(path).split("\\")[-1].split("/")[-1].replace(".wav", "")
        v, a = anchors[q]
        return {"rec_arousal": a, "rec_valence": v, "rec_dominance": 0.0}
    monkeypatch.setattr(ec, "predict_va", fake)

    out = tmp_path / "emotion.csv"
    assert ec.main(["--register", str(reg), "--out", str(out)]) == 0
    got = list(csv.DictReader(open(out, encoding="utf-8")))
    assert len(got) == 4
    assert all(r["rec_quadrant"] == r["quadrant"] for r in got)      # recovered every quadrant
    printed = capsys.readouterr().out
    assert "Emotion conveyance per engine" in printed and "Confusion" in printed


def test_output_never_overwrites(tmp_path, monkeypatch):
    p = tmp_path / "a.wav"
    _wav(p)
    reg = tmp_path / "register.csv"
    _register(reg, [{"audio_path": str(p), "engine": "kokoro", "param_set": "rate_volume_pitch",
                     "quadrant": "Q1", "valence": 0.6, "arousal": 0.6, "silent": "no"}])
    monkeypatch.setattr(ec, "predict_va",
                        lambda path, model_id=None: {"rec_arousal": 0.1, "rec_valence": 0.1,
                                                     "rec_dominance": 0.0})
    assert ec.main(["--register", str(reg)]) == 0
    assert ec.main(["--register", str(reg)]) == 0
    assert len(list(tmp_path.glob("emotion*.csv"))) == 2
