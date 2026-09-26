"""CLI demo: the MVP definition of done, executable.

    echo-run "I lost my keys again" --quadrant Q2
    echo-run "I lost my keys again" --all-quadrants
    echo-run "I lost my keys again" --quadrant Q2 --engine sapi     # pick the TTS engine
    echo-run "I lost my keys again" --all-quadrants --mock --engine kokoro   # mock LLM, real voice

One message -> emotion-conditioned reply -> coherence check -> speech whose rate,
loudness and pitch reflect the emotion -> one full SQLite row -> audio plays.

--engine overrides config (ECHO_TTS_ENGINE); --mock uses the silent mock engine unless
--engine says otherwise.
"""

from __future__ import annotations

import argparse
import platform
import sys

from judge import make_judge
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
    detected = acc.self_quadrant.value if acc.self_quadrant else "no-opinion"
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
    parser.add_argument("message", nargs="?", help="the incoming message to reply to")
    parser.add_argument("--quadrant", choices=[q.value for q in Quadrant], help="single target emotion")
    parser.add_argument("--all-quadrants", action="store_true", help="sweep Q1..Q4")
    parser.add_argument("--mock", action="store_true", help="use mock LLM/TTS (no external tools)")
    parser.add_argument("--engine", choices=["auto", "mock", "pyttsx3", "sapi", "sapi5xml",
                                             "espeak", "kokoro", "chatterbox", "zipvoice"],
                        default=None, help="TTS engine (overrides config ECHO_TTS_ENGINE)")
    parser.add_argument("--list-engines", action="store_true",
                        help="print the per-engine capability matrix and exit")
    parser.add_argument("--no-audio", action="store_true", help="synthesise but do not play")
    parser.add_argument("--judge",
                        choices=["self-report", "blind-llm", "lexicon", "cascade"],
                        help="who decides the emotion of the reply (default from config; "
                             "self-report is L0 legacy and leaks the target)")
    args = parser.parse_args(argv)

    if args.list_engines:
        from tts import format_capability_matrix
        print("Per-engine capability matrix (which dials each engine renders):")
        print(format_capability_matrix())
        return 0

    if not args.message:
        parser.error("message is required (or use --list-engines)")
    if not args.quadrant and not args.all_quadrants:
        parser.error("choose --quadrant Qn or --all-quadrants")

    cfg = load_config()
    quadrants = list(Quadrant) if args.all_quadrants else [Quadrant(args.quadrant)]

    strategy = SymmetricStrategy(voice_id=cfg.kokoro_voice)

    if args.mock:
        llm = MockLLMAdapter()
    else:
        try:
            llm = OllamaAdapter(
                cfg.ollama_host, cfg.ollama_model,
                temperature=cfg.llm_temperature, timeout_s=cfg.llm_timeout_s,
            )
            llm.ping()          # fail fast and readably if the server is not up
        except Exception as exc:
            print(f"ERROR: could not reach Ollama at {cfg.ollama_host} ({exc}).")
            print("Is `ollama serve` running and the model pulled? Or try --mock.")
            return 2

    engine_choice = args.engine or ("mock" if args.mock else cfg.tts_engine)
    tts = make_tts(engine_choice, kokoro_model=cfg.kokoro_model_path,
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

    judge = make_judge(args.judge or cfg.judge, llm=llm, norms_path=cfg.affect_norms or None)

    store = ProvenanceStore(cfg.db_path)
    print(f'message: "{args.message}"   [db={cfg.db_path}, tts={tts.engine_id}, '
          f'judge={judge.judge_id} L{judge.level}]')

    for q in quadrants:
        contract = EmotionContract.from_quadrant(q)
        rec = run_turn(
            contract, args.message,
            strategy=strategy, llm=llm, tts=tts, store=store,
            audio_dir=cfg.audio_dir, max_retries=cfg.max_retries,
            judge=judge, llm_temperature=cfg.llm_temperature,
        )
        _print_turn(rec)
        if not args.no_audio:
            _play(rec.audio_path)

    store.close()
    print(f"\nDone. {len(quadrants)} turn(s) logged to {cfg.db_path}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
