"""Blinded listening-test kit (Story S1.0): the set must be balanced, blinded, randomised
and reproducible, and scoring must recover MOS + emotion accuracy from the answer sheet."""

import csv
import wave

import make_listening_test as mlt


def _wav(p):
    with wave.open(str(p), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(b"\x00\x00" * 1600)


def _register(tmp_path):
    rows = []
    for eng in ("sapi5xml", "kokoro"):
        for q in ("Q1", "Q2", "Q3", "Q4"):
            p = tmp_path / f"{eng}_{q}.wav"
            _wav(p)
            rows.append({"audio_path": str(p), "engine": eng, "param_set": "rate_volume_pitch",
                         "quadrant": q, "stimulus_id": "S01", "silent": "no"})
    reg = tmp_path / "register.csv"
    with open(reg, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    return reg


def test_build_is_balanced_blinded_and_keyed(tmp_path):
    reg = _register(tmp_path)
    out = tmp_path / "listening"
    assert mlt.main(["--build", "--register", str(reg), "--out-root", str(out), "--per-engine", "4"]) == 0

    session = next(out.glob("*_pilot"))
    clips = sorted((session / "clips").glob("*.wav"))
    assert len(clips) == 8                                   # 2 engines x 4 quadrants
    assert all(c.stem.isdigit() for c in clips)              # blinded: opaque numeric IDs only

    key = list(csv.DictReader(open(session / "key.csv", encoding="utf-8")))
    assert len(key) == 8
    assert {r["engine"] for r in key} == {"sapi5xml", "kokoro"}          # balanced engines
    assert {r["quadrant"] for r in key} == {"Q1", "Q2", "Q3", "Q4"}      # balanced quadrants

    ans = list(csv.DictReader(open(session / "answers.csv", encoding="utf-8")))
    assert len(ans) == 8 and all(a["naturalness_1to5"] == "" for a in ans)   # blank sheet
    assert (session / "INSTRUCTIONS.md").exists()


def test_scoring_recovers_mos_and_emotion_accuracy(tmp_path, capsys):
    reg = _register(tmp_path)
    out = tmp_path / "listening"
    mlt.main(["--build", "--register", str(reg), "--out-root", str(out), "--per-engine", "4"])
    session = next(out.glob("*_pilot"))

    # simulated listener: kokoro rated 5 and always identified correctly; sapi rated 3, always wrong
    key = {r["blind_id"]: r for r in csv.DictReader(open(session / "key.csv", encoding="utf-8"))}
    rows = []
    for bid, k in key.items():
        if k["engine"] == "kokoro":
            rows.append({"blind_id": bid, "naturalness_1to5": "5", "emotion_guess": k["quadrant"], "notes": ""})
        else:
            wrong = "Q2" if k["quadrant"] != "Q2" else "Q1"
            rows.append({"blind_id": bid, "naturalness_1to5": "3", "emotion_guess": wrong, "notes": ""})
    with open(session / "answers.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["blind_id", "naturalness_1to5", "emotion_guess", "notes"])
        w.writeheader()
        w.writerows(rows)

    assert mlt.main(["--score", "--session", str(session)]) == 0
    out_text = capsys.readouterr().out
    assert "kokoro" in out_text and "5.00" in out_text and "100%" in out_text
    assert "3.00" in out_text and "Confusion" in out_text


def test_scoring_survives_excel_stripping_leading_zeros(tmp_path, capsys):
    """Excel saves '001' as '1'; scoring must still join to key.csv."""
    reg = _register(tmp_path)
    out = tmp_path / "listening"
    mlt.main(["--build", "--register", str(reg), "--out-root", str(out), "--per-engine", "4"])
    session = next(out.glob("*_pilot"))

    key = {r["blind_id"]: r for r in csv.DictReader(open(session / "key.csv", encoding="utf-8"))}
    rows = [{"blind_id": str(int(bid)),                    # "001" -> "1", as Excel would write it
             "naturalness_1to5": "4", "emotion_guess": k["quadrant"], "notes": ""}
            for bid, k in key.items()]
    with open(session / "answers.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["blind_id", "naturalness_1to5", "emotion_guess", "notes"])
        w.writeheader()
        w.writerows(rows)

    assert mlt.main(["--score", "--session", str(session)]) == 0
    text = capsys.readouterr().out
    assert "4.00" in text and "100%" in text          # joined correctly despite the id mangling
