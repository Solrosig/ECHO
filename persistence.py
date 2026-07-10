"""Provenance store — PROTECTED SEAM #3.

One row per turn + one row per attempt. The whole turn is written in a single
transaction, so a failure leaves zero orphan rows. Later evaluation reads only
from this log; it never inspects live model state.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone

from contracts import EmotionContract
from gate import Attempt
from strategies import VoiceParams

_SCHEMA = """
CREATE TABLE IF NOT EXISTS turns (
    turn_uuid      TEXT PRIMARY KEY,
    ts             TEXT NOT NULL,
    message        TEXT NOT NULL,
    intent         TEXT NOT NULL,
    quadrant       TEXT NOT NULL,
    valence        REAL NOT NULL,
    arousal        REAL NOT NULL,
    intensity      REAL NOT NULL,
    strategy       TEXT NOT NULL,
    prompt_version TEXT NOT NULL,
    anchor_version TEXT NOT NULL,
    model          TEXT NOT NULL,
    reply          TEXT NOT NULL,
    self_quadrant  TEXT,
    gate_passed    INTEGER NOT NULL,
    n_attempts     INTEGER NOT NULL,
    voice_id       TEXT NOT NULL,
    rate           REAL NOT NULL,
    engine         TEXT NOT NULL,
    audio_path     TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS attempts (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    turn_uuid     TEXT NOT NULL REFERENCES turns(turn_uuid),
    attempt_index INTEGER NOT NULL,
    reply         TEXT NOT NULL,
    self_quadrant TEXT,
    passed        INTEGER NOT NULL,
    accepted      INTEGER NOT NULL,
    raw           TEXT
);
"""


@dataclass
class TurnRecord:
    contract: EmotionContract
    message: str
    strategy: str
    prompt_version: str
    model: str
    attempts: list[Attempt]
    voice_params: VoiceParams
    engine: str
    audio_path: str

    @property
    def accepted(self) -> Attempt:
        return next(a for a in self.attempts if a.accepted)

    @property
    def gate_passed(self) -> bool:
        return any(a.passed for a in self.attempts)


class ProvenanceStore:
    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        self._conn = sqlite3.connect(db_path)
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def save_turn(self, rec: TurnRecord) -> str:
        c = rec.contract
        accepted = rec.accepted
        with self._conn:  # transaction: commit on success, rollback on error
            self._conn.execute(
                "INSERT INTO turns VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    c.turn_uuid,
                    datetime.now(timezone.utc).isoformat(),
                    rec.message,
                    c.intent,
                    c.quadrant.value,
                    c.valence,
                    c.arousal,
                    c.intensity,
                    rec.strategy,
                    rec.prompt_version,
                    c.anchor_version,
                    rec.model,
                    accepted.reply,
                    accepted.self_quadrant.value if accepted.self_quadrant else None,
                    int(rec.gate_passed),
                    len(rec.attempts),
                    rec.voice_params.voice_id,
                    rec.voice_params.rate,
                    rec.engine,
                    rec.audio_path,
                ),
            )
            self._conn.executemany(
                "INSERT INTO attempts "
                "(turn_uuid, attempt_index, reply, self_quadrant, passed, accepted, raw) "
                "VALUES (?,?,?,?,?,?,?)",
                [
                    (
                        c.turn_uuid,
                        a.index,
                        a.reply,
                        a.self_quadrant.value if a.self_quadrant else None,
                        int(a.passed),
                        int(a.accepted),
                        a.raw,
                    )
                    for a in rec.attempts
                ],
            )
        return c.turn_uuid

    def read_turn(self, turn_uuid: str) -> dict:
        self._conn.row_factory = sqlite3.Row
        turn = self._conn.execute(
            "SELECT * FROM turns WHERE turn_uuid=?", (turn_uuid,)
        ).fetchone()
        attempts = self._conn.execute(
            "SELECT * FROM attempts WHERE turn_uuid=? ORDER BY attempt_index", (turn_uuid,)
        ).fetchall()
        return {
            "turn": dict(turn) if turn else None,
            "attempts": [dict(a) for a in attempts],
        }

    def close(self) -> None:
        self._conn.close()
