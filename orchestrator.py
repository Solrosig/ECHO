"""The per-turn pipeline: contract -> strategy -> LLM (gated) -> TTS -> log.

Plain library, callable from the CLI (and later a UI or batch runner). It never
imports evaluation code — data flows one way, into the provenance log.
"""

from __future__ import annotations

from pathlib import Path

from llm import LLMAdapter
from tts import TTSAdapter
from contracts import EmotionContract
from gate import run_gated
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
) -> TurnRecord:
    """Run one message + emotion end-to-end and persist it. Returns the record."""
    prompt = strategy.build_prompt(contract, message)

    attempts = run_gated(lambda: llm.generate(prompt), contract.quadrant, max_retries=max_retries)
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
    )
    store.save_turn(record)
    return record
