"""Per-engine capability matrix (Story N1.2). Keeps engine comparisons honest by
declaring which dials each engine actually renders."""

import tts


def test_capability_matrix_covers_engines_and_dials():
    m = {r["engine"]: r for r in tts.capability_matrix()}
    assert {"mock", "pyttsx3", "sapi5xml", "kokoro"} <= set(m)
    # honest, engine-specific rendering:
    assert m["pyttsx3"]["rate"] == "yes" and m["pyttsx3"]["pitch"] == "no"   # no pitch
    assert m["sapi5xml"]["pitch"] == "yes"                                    # full dial set
    assert m["kokoro"]["natural"] == "yes"                                    # neural voice
    assert m["mock"]["rate"] == "no"                                          # silent -> renders nothing


def test_format_capability_matrix_is_readable_text():
    s = tts.format_capability_matrix()
    assert "engine" in s and "sapi5xml" in s and "pitch" in s
