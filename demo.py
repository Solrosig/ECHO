"""CLI demo — the MVP definition of done, executable.

    echo-run "I lost my keys again" --quadrant Q2
    echo-run "I lost my keys again" --all-quadrants

One message -> emotion-conditioned reply -> coherence check -> speech whose pace
reflects arousal -> one full SQLite row -> audio plays.
"""

from __future__ import annotations

import argparse
import platform
import sys

from llm import MockLLMAdapter, OllamaAdapter
from tts import make_tts
from config import load_config
from contracts import EmotionContract, Quadrant
from orchestrator import run_turn
from persistence import ProvenanceStore
from strategies import SymmetricStrategy


def _play(path: str) -> None:
    """Best-effort audio playback (Windows)."""
    try:
        if platform.system() == "Windows":
            import winsound

            winsound.PlaySound(path, winsound.SND_FILENAME)
        else:
            print(f"   (audio saved; play it manually: {path})")
    except Exception as exc:  # never let playback crash the demo
        print(f"   (could not auto-play {path}: {exc})")


def _print_turn(rec) -> None:
    c = rec.contract
    acc = rec.accepted
    detected = acc.self_quadrant.value if acc.self_quadrant else "unparsed"
    mark = "PASS" if rec.gate_passed else "no-match"
    vp = rec.voice_params
    print(f"\n== {c.quadrant.value} ({c.label}) | val={c.valence:+.1f} aro={c.arousal:+.1f}"
          f" -> rate={vp.rate:.2f} vol={vp.volume:.2f} pitch={vp.pitch:.2f} ==")
    print(f"   reply     : {acc.reply}")
    print(f"   coherence : target={c.quadrant.value} detected={detected} [{mark}] "
          f"after {len(rec.attempts)} attempt(s)")
    print(f"   audio     : {rec.audio_path}  (engine={rec.engine})")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="echo-run", description="ECHO MVP demo")
    parser.add_argument("message", help="the incoming message to reply to")
    parser.add_argument("--quadrant", choices=[q.value for q in Quadrant], help="single target emotion")
    parser.add_argument("--all-quadrants", action="store_true", help="sweep Q1..Q4")
    parser.add_argument("--mock", action="store_true", help="use mock LLM/TTS (no external tools)")
    parser.add_argument("--no-audio", action="store_true", help="synthesise but do not play")
    args = parser.parse_args(argv)

    if not args.quadrant and not args.all_quadrants:
        parser.error("choose --quadrant Qn or --all-quadrants")

    cfg = load_config()
    quadrants = list(Quadrant) if args.all_quadrants else [Quadrant(args.quadrant)]

    strategy = SymmetricStrategy(voice_id=cfg.kokoro_voice)
    if args.mock:
        from tts import MockTTSAdapter

        llm = MockLLMAdapter()
        tts = MockTTSAdapter()
    else:
        try:
            llm = OllamaAdapter(
                cfg.ollama_host, cfg.ollama_model,
                temperature=cfg.llm_temperature, timeout_s=cfg.llm_timeout_s,
            )
        except Exception as exc:
            print(f"ERROR: could not reach Ollama at {cfg.ollama_host} ({exc}).")
            print("Is `ollama serve` running and the model pulled? Or try --mock.")
            return 2
        tts = make_tts(cfg.tts_engine, kokoro_model=cfg.kokoro_model_path,
                       kokoro_voices=cfg.kokoro_voices_path)

    store = ProvenanceStore(cfg.db_path)
    print(f'message: "{args.message}"   [db={cfg.db_path}, tts={tts.engine_id}]')

    for q in quadrants:
        contract = EmotionContract.from_quadrant(q)
        rec = run_turn(
            contract, args.message,
            strategy=strategy, llm=llm, tts=tts, store=store,
            audio_dir=cfg.audio_dir, max_retries=cfg.max_retries,
        )
        _print_turn(rec)
        if not args.no_audio:
            _play(rec.audio_path)

    store.close()
    print(f"\nDone. {len(quadrants)} turn(s) logged to {cfg.db_path}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
