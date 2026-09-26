"""The per-turn pipeline: contract -> strategy -> LLM (gated) -> TTS -> log.

Plain library, callable from the CLI. It never imports evaluation code: data flows one
way, into the provenance log.
"""

from __future__ import annotations

from pathlib import Path

from llm import LLMAdapter
from tts import TTSAdapter
from contracts import EmotionContract
from gate import run_gated
from judge import EmotionJudge, SelfReportJudge
from persistence import ProvenanceStore, TurnRecord
from strategies import PROMPT_VERSION, EncodingStrategy


def run_turn(
    contract: EmotionContract,
    message: str,
    *,
    strategy: EncodingStrategy,
    llm: LLMAdapter,
    tts: TTSAdapter,
    store: ProvenanceStore,
    audio_dir: str,
    max_retries: int = 2,
    judge: EmotionJudge | None = None,
    llm_temperature: float | None = None,
) -> TurnRecord:
    """Run one message + emotion end-to-end and persist it. Returns the record.

    `judge` defaults to the legacy self-report judge so existing callers keep working,
    but that is L0 (no independence) and not defensible for a reported result. Pass an
    independent judge; its level is recorded with the turn.
    """
    prompt = strategy.build_prompt(contract, message)
    judge = judge or SelfReportJudge()

    attempts = run_gated(
        lambda: llm.generate(prompt), contract.quadrant,
        max_retries=max_retries, judge=judge,
    )
    accepted = next(a for a in attempts if a.accepted)

    voice_params = strategy.build_voice_params(contract)
    audio_path = Path(audio_dir) / f"{contract.turn_uuid}_{contract.quadrant.value}.wav"
    tts.synthesize(accepted.reply, voice_params, audio_path)

    record = TurnRecord(
        contract=contract,
        message=message,
        strategy=strategy.name,
        prompt_version=PROMPT_VERSION,
        model=llm.model_id,
        attempts=attempts,
        voice_params=voice_params,
        engine=tts.engine_id,
        audio_path=str(audio_path),
        judge_id=judge.judge_id,
        judge_level=judge.level,
        llm_temperature=llm_temperature,
    )
    store.save_turn(record)
    return record
