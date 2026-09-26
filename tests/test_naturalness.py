"""Naturalness scorer (Story N4). The UTMOS predictor (torch/librosa) is mocked so the
pipeline — register I/O, per-engine ranking, non-overwrite output — is tested without the
heavy deps. The real predictor runs only on a machine with torch installed."""

import csv
import wave

import naturalness


def _wav(p):
    with wave.open(str(p), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(22050)
        w.writeframes(b"\x00\x00" * 2205)        # 0.1 s of silence — content irrelevant (predictor mocked)


def _register(path, rows):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["audio_path", "engine", "param_set", "quadrant", "silent"])
        w.writeheader()
        w.writerows(rows)


def test_scores_and_ranks_engines(tmp_path, monkeypatch):
    sap, kok = tmp_path / "sapi.wav", tmp_path / "kok.wav"
    _wav(sap)
    _wav(kok)
    reg = tmp_path / "register.csv"
    _register(reg, [
        {"audio_path": str(sap), "engine": "sapi5xml", "param_set": "rate_volume_pitch", "quadrant": "Q1", "silent": "no"},
        {"audio_path": str(kok), "engine": "kokoro", "param_set": "rate_volume_pitch", "quadrant": "Q1", "silent": "no"},
    ])
    monkeypatch.setattr(naturalness, "predict_mos", lambda p: 4.2 if "kok" in str(p) else 2.9)

    out = tmp_path / "naturalness.csv"
    assert naturalness.main(["--register", str(reg), "--out", str(out)]) == 0
    got = list(csv.DictReader(open(out, encoding="utf-8")))
    assert len(got) == 2 and all("utmos" in r for r in got)
    by = {r["engine"]: float(r["utmos"]) for r in got}
    assert by["kokoro"] > by["sapi5xml"]         # more-natural engine ranks higher


def test_confound_check_reports_engine_vs_dial_spread(tmp_path, monkeypatch, capsys):
    """M3: the summary must show mean UTMOS per engine x param_set and judge whether the
    engine effect dominates ECHO's own dial settings."""
    rows, scores = [], {}
    for eng, base in (("kokoro", 4.5), ("espeak", 2.1)):
        for ps in ("neutral", "rate_volume_pitch"):
            p = tmp_path / f"{eng}_{ps}.wav"
            _wav(p)
            rows.append({"audio_path": str(p), "engine": eng, "param_set": ps,
                         "quadrant": "Q1", "silent": "no"})
            scores[str(p)] = base - (0.05 if ps != "neutral" else 0.0)   # small dial effect
    reg = tmp_path / "register.csv"
    _register(reg, rows)
    monkeypatch.setattr(naturalness, "predict_mos", lambda p: scores[str(p)])

    assert naturalness.main(["--register", str(reg), "--out", str(tmp_path / "n.csv")]) == 0
    text = capsys.readouterr().out
    assert "Confound check" in text and "neutral" in text
    assert "PASS" in text          # engine spread (2.4) >> dial spread (0.05)


def test_confound_check_gives_each_ab_condition_its_own_cells(capsys):
    """An engine run in several sessions (an A/B condition pair) gets one confound row per
    condition, and each row must read its own param-set cells, so its real dial spread
    reaches the verdict."""
    a, b = "chatterbox [chatterbox_x2]", "chatterbox [chatterbox_x2_refs]"
    rows = [
        {"engine": eng, "session": sess, "param_set": ps, "utmos": mos}
        for eng, sess, neutral, full in (
            ("chatterbox", "2026-07-30_0217_chatterbox_x2", 4.0, 3.0),         # dial spread 1.0
            ("chatterbox", "2026-08-09_1911_chatterbox_x2_refs", 3.75, 3.5),   # dial spread 0.25
            ("kokoro", "2026-07-27_0015_kokoro_check", 4.5, 4.25),             # dial spread 0.25
        )
        for ps, mos in (("neutral", neutral), ("rate_volume_pitch", full))
    ]
    naturalness._summary(rows)
    confound = capsys.readouterr().out.split("Confound check", 1)[1]

    def row(label):              # -> [neutral, rate_volume_pitch, dial spread] as printed
        return next((ln.split()[-3:] for ln in confound.splitlines()
                     if ln.startswith(f"  {label} ")), None)

    assert row(a) == ["4.000", "3.000", "1.000"]
    assert row(b) == ["3.750", "3.500", "0.250"]
    assert row("kokoro") == ["4.500", "4.250", "0.250"]
    # real max dial spread is condition A's 1.0, not kokoro's 0.25: ratio 0.875 / 1.0 < 3
    assert "max dial spread 1.000" in confound
    assert "CHECK" in confound and "PASS" not in confound


def test_output_never_overwrites(tmp_path, monkeypatch):
    w = tmp_path / "a.wav"
    _wav(w)
    reg = tmp_path / "register.csv"
    _register(reg, [{"audio_path": str(w), "engine": "kokoro", "param_set": "neutral", "quadrant": "Q1", "silent": "no"}])
    monkeypatch.setattr(naturalness, "predict_mos", lambda p: 4.0)
    assert naturalness.main(["--register", str(reg)]) == 0          # -> naturalness.csv
    assert naturalness.main(["--register", str(reg)]) == 0          # -> timestamped sibling
    assert len(list(tmp_path.glob("naturalness*.csv"))) == 2
