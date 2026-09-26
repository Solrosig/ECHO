"""Controlled synthesis harness for the TTS / parameter comparison.

Renders the fixed stimuli through a chosen engine and parameter set(s), across all
four quadrants, into a documented session folder. The text is constant across every
condition, so only prosody varies (isolating the voice channel). The LLM is bypassed:
this is a voice-rendering experiment, not a live system run.

Each run creates:
    research/sessions/<YYYY-MM-DD_HHMM>_<label>/
        audio/<engine>/<param_set>/<stimulus>_<quadrant>.wav   (neutral/ = flat Before)
        register.csv   (one row per clip: dials, stimulus, target, hash, duration_ok)
        SESSION.md     (purpose, config, git commit/tag, stimuli, what to compare)

Usage:
    python synth_stimuli.py --engine sapi --param-set all --label sapi_ablation \
        --purpose "Ablation of the voice dials on the SAPI engine at v0.2."

  --engine     pyttsx3 | sapi | espeak | kokoro | chatterbox | zipvoice | styletts2 |
               cosyvoice2 | parlertts | mock
  --param-set  neutral | rate | rate_volume | rate_volume_pitch | all   (neutral = flat Before)
  --label      short slug for the session folder
  --purpose    one-line objective recorded in SESSION.md
  --stimuli    stimuli_eval.txt        --sessions-root  research/sessions
"""

from __future__ import annotations

import argparse
import contextlib
import csv
import hashlib
import subprocess
import wave
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

from config import load_config
from contracts import EmotionContract, Quadrant
from strategies import SymmetricStrategy
from tts import make_tts

PARAM_SETS = ["neutral", "rate", "rate_volume", "rate_volume_pitch"]
REGISTER_FIELDS = [
    "clip_id", "blind_id", "created", "engine", "param_set", "stimulus_id", "quadrant",
    "valence", "arousal", "intensity", "rate", "volume", "pitch", "pitch_rendered",
    "duration_s", "duration_ok", "model", "text", "audio_path", "sha256", "commit", "tag",
]


def load_stimuli(path: str) -> list[tuple[str, str]]:
    items: list[tuple[str, str]] = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        sid, _, text = line.partition(":")
        items.append((sid.strip(), text.strip()) if text else (f"S{len(items)+1:02d}", line))
    return items


def apply_param_set(vp, param_set: str):
    """Mask voice dials for the ablation.

    'neutral' is the true Before (no emotion in the voice at all: a flat carrier); 'rate'
    adds only speed (the MVP baseline); then volume; then pitch (the full After). 'neutral'
    vs 'rate_volume_pitch' on the same clip is the clear, audible Before/After; the
    rate -> ... -> full steps are the subtle per-dial research ablation.
    """
    if param_set == "neutral":
        # A true baseline must be emotionless for every engine class, so the emotion fields
        # are zeroed as well as the prosody dials. Otherwise an engine that conditions natively
        # (e.g. Chatterbox: exaggeration<-arousal, reference style<-quadrant) would still get
        # the full emotion here and "neutral" would silently not be neutral.
        return replace(vp, rate=1.0, volume=1.0, pitch=1.0,
                       valence=0.0, arousal=0.0, intensity=0.0, quadrant="")
    if param_set == "rate":
        return replace(vp, volume=1.0, pitch=1.0)   # arousal->rate only (= MVP baseline)
    if param_set == "rate_volume":
        return replace(vp, pitch=1.0)
    return vp                                        # full: rate + volume + pitch


def sha256_file(p: Path) -> str:
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def wav_duration(p: Path):
    try:
        with contextlib.closing(wave.open(str(p), "rb")) as w:
            return round(w.getnframes() / float(w.getframerate()), 3)
    except Exception:
        return None


def clip_id_for(engine: str, param_set: str, sid: str, quad: str) -> str:
    return hashlib.sha256(f"{engine}|{param_set}|{sid}|{quad}".encode()).hexdigest()[:10]


def _git(args: list[str]) -> str:
    try:
        return subprocess.run(["git", *args], capture_output=True, text=True, timeout=10).stdout.strip()
    except Exception:
        return ""


def engine_settings(engine_id: str, cfg) -> dict:
    """Engine settings that define this condition, for the session record.

    Conditions often differ by a setting rather than an engine: Chatterbox A/B/C differed in
    reference clips, and the ZipVoice conditions differ in prompt normalisation and reference
    set. When the session recorded only the engine name, the operator's label was the sole
    distinction, and a mistyped label would have silently mislabelled a whole condition.
    """
    if engine_id == "zipvoice":
        return {
            "refs": cfg.zipvoice_refs,
            "model": cfg.zipvoice_model,
            "seed": cfg.zipvoice_seed,
            "target_rms": cfg.zipvoice_target_rms,
            "num_step": cfg.zipvoice_num_step or "(model default)",
        }
    if engine_id == "chatterbox":
        return {"refs": cfg.chatterbox_refs or "(none)", "device": cfg.chatterbox_device}
    if engine_id == "kokoro":
        return {"voice": cfg.kokoro_voice}
    return {}


def _write_session_md(path: Path, purpose: str, engine_id: str, param_sets: list[str],
                      stimuli: list[tuple[str, str]], commit: str, tag: str,
                      n_clips: int, n_flagged: int, band: tuple[float, float],
                      settings: "dict | None" = None) -> None:
    lines = [
        f"# Generation session — {path.parent.name}",
        "",
        f"- **Created (UTC):** {datetime.now(timezone.utc).isoformat()}",
        f"- **Purpose / objective:** {purpose or '(not given)'}",
        f"- **Engine:** `{engine_id}`",
        ("- **Engine settings:** "
         + ", ".join(f"`{k}={v}`" for k, v in (settings or {}).items())
         if settings else "- **Engine settings:** (none recorded for this engine)"),
        f"- **Parameter sets:** {', '.join(param_sets)}",
        f"- **Git commit:** `{commit or 'unknown'}`   **nearest tag:** `{tag or 'none'}`",
        f"- **Stimuli:** {len(stimuli)} fixed neutral sentences ({', '.join(s for s, _ in stimuli)})",
        f"- **Quadrants:** Q1–Q4   ·   **Clips:** {n_clips}   ·   "
        f"**flagged out-of-band [{band[0]}–{band[1]} s]:** {n_flagged}",
        "",
        "## What to compare",
        "- **Before vs After (clearest):** `neutral/<clip>` (flat, emotionless voice) vs "
        "`rate_volume_pitch/<clip>` for the SAME file, e.g. `S01_Q1.wav` -> the voice goes from "
        "neutral to expressive. (`neutral/` sounds identical across quadrants -- that is the point.)",
        "- **Emotion distinction:** within `rate_volume_pitch/`, compare `S01_Q1` (happy) vs `S01_Q3` (sad).",
        "- **Ablation (per-dial, subtle):** `rate/` -> `rate_volume/` -> `rate_volume_pitch/` isolates each "
        "dial's marginal effect. This is the research view, NOT the demo (differences here are small).",
        "- Against other sessions/engines at the same or a different **tag** (the evolution).",
        "",
        "## Files",
        "- `register.csv` — one row per clip (dials, stimulus, target, SHA-256, duration_ok).",
        "- `audio/<engine>/<param_set>/<stimulus>_<quadrant>.wav` — clips share a name across param-set "
        "folders for trivial A/B (git-ignored; back up separately).",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _new_session_dir(root: Path, label: str) -> Path:
    """Return a fresh session folder path, never an existing one.

    The stamp has minute resolution, so two runs in the same minute under the same label used
    to share a folder (`exist_ok=True`) and silently overwrite the clips, register.csv and
    SESSION.md. Every generated audio set must be kept for analysis and reporting, so a
    collision yields `..._label-2`, `-3`, … instead.
    """
    stamp = datetime.now().strftime("%Y-%m-%d_%H%M")
    cand = root / f"{stamp}_{label}"
    i = 2
    while cand.exists():
        cand = root / f"{stamp}_{label}-{i}"
        i += 1
    return cand


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--engine", default="pyttsx3")
    ap.add_argument("--param-set", default="all",
                    choices=["neutral", "rate", "rate_volume", "rate_volume_pitch", "all"])
    ap.add_argument("--label", default="session")
    ap.add_argument("--purpose", default="")
    ap.add_argument("--stimuli", default="stimuli_eval.txt")
    ap.add_argument("--sessions-root", default="research/sessions")
    args = ap.parse_args(argv)

    cfg = load_config()
    tts = make_tts(args.engine, kokoro_model=cfg.kokoro_model_path,
                   kokoro_voices=cfg.kokoro_voices_path,
                   chatterbox_refs=cfg.chatterbox_refs, chatterbox_device=cfg.chatterbox_device,
                   chatterbox_model=cfg.chatterbox_model,
                   zipvoice_refs=cfg.zipvoice_refs, zipvoice_python=cfg.zipvoice_python,
                   zipvoice_model=cfg.zipvoice_model, zipvoice_model_dir=cfg.zipvoice_model_dir,
                   zipvoice_seed=cfg.zipvoice_seed, zipvoice_num_step=cfg.zipvoice_num_step,
                   zipvoice_target_rms=cfg.zipvoice_target_rms,
                   zipvoice_threads=cfg.zipvoice_threads,
                   zipvoice_repo=cfg.zipvoice_repo,
                   zipvoice_vocoder=cfg.zipvoice_vocoder)
    engine_id = tts.engine_id
    strat = SymmetricStrategy(voice_id=cfg.kokoro_voice)
    stimuli = load_stimuli(args.stimuli)
    param_sets = PARAM_SETS if args.param_set == "all" else [args.param_set]
    commit, tag = _git(["rev-parse", "--short", "HEAD"]), _git(["describe", "--tags", "--abbrev=0"])

    session_dir = _new_session_dir(Path(args.sessions_root), args.label)
    session_dir.mkdir(parents=True, exist_ok=False)

    rows: list[dict] = []
    n_flagged = 0
    total = len(param_sets) * len(stimuli) * len(list(Quadrant))
    done = 0
    print(f"Synthesising {total} clips with {engine_id} (first neural clip loads the model — please wait)...",
          flush=True)
    for ps in param_sets:
        for sid, text in stimuli:
            for q in Quadrant:
                c = EmotionContract.from_quadrant(q)
                vp = apply_param_set(strat.build_voice_params(c), ps)
                cid = clip_id_for(engine_id, ps, sid, q.value)
                # Stimulus + quadrant filename: the same words get the same name in every
                # param-set folder, for easy Before/After comparison.
                dest = session_dir / "audio" / engine_id / ps / f"{sid}_{q.value}.wav"
                tts.synthesize(text, vp, dest)
                done += 1
                print(f"  [{done}/{total}] {engine_id}/{ps}/{sid}_{q.value}", flush=True)
                dur = wav_duration(dest)
                ok = dur is not None and cfg.min_duration_s <= dur <= cfg.max_duration_s
                n_flagged += 0 if ok else 1
                rows.append({
                    "clip_id": cid,
                    "blind_id": "B" + hashlib.sha256(cid.encode()).hexdigest()[:6],
                    "created": datetime.now(timezone.utc).isoformat(),
                    "engine": engine_id, "param_set": ps, "stimulus_id": sid, "quadrant": q.value,
                    "valence": c.valence, "arousal": c.arousal, "intensity": c.intensity,
                    "rate": round(vp.rate, 3), "volume": round(vp.volume, 3), "pitch": round(vp.pitch, 3),
                    "pitch_rendered": "yes" if "pitch" in getattr(tts, "renders", frozenset()) else "no",
                    "duration_s": dur, "duration_ok": "yes" if ok else "no",
                    "model": "fixed-text", "text": text, "audio_path": str(dest),
                    "sha256": sha256_file(dest), "commit": commit, "tag": tag,
                })

    reg = session_dir / "register.csv"
    with open(reg, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=REGISTER_FIELDS)
        w.writeheader()
        w.writerows(rows)
    _write_session_md(session_dir / "SESSION.md", args.purpose, engine_id, param_sets,
                      stimuli, commit, tag, len(rows), n_flagged,
                      (cfg.min_duration_s, cfg.max_duration_s),
                      engine_settings(engine_id, cfg))

    print(f"Session: {session_dir}")
    print(f"  clips: {len(rows)}  ({engine_id}; param-sets: {', '.join(param_sets)})")
    print(f"  register: {reg}   +   SESSION.md")
    if n_flagged:
        print(f"  WARNING: {n_flagged} clip(s) outside the duration band "
              f"[{cfg.min_duration_s}, {cfg.max_duration_s}] s — flagged duration_ok=no (exclude from analysis).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
