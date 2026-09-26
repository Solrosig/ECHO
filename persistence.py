"""Provenance store (protected seam #3).

One row per turn plus one per attempt, written in a single transaction so a failure
leaves no orphan rows. Evaluation reads only this log, never live model state.
Records the full voice control: rate, volume and pitch.
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
    volume         REAL,
    pitch          REAL,
    engine         TEXT NOT NULL,
    audio_path     TEXT NOT NULL,
    -- G6 (2026-08-23): how the emotion was judged, and how independent that judge was.
    -- Recorded per turn so every result declares its own independence level rather
    -- than leaving it to be inferred from the commit date.
    judge_id       TEXT,
    judge_level    INTEGER,
    llm_temperature REAL
);

CREATE TABLE IF NOT EXISTS attempts (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    turn_uuid     TEXT NOT NULL REFERENCES turns(turn_uuid),
    attempt_index INTEGER NOT NULL,
    reply         TEXT NOT NULL,
    self_quadrant TEXT,
    passed        INTEGER NOT NULL,
    accepted      INTEGER NOT NULL,
    raw           TEXT,
    judged_by     TEXT,
    judge_level   INTEGER
);
"""

# Explicit column order for the turns INSERT (robust to future schema growth).
_TURN_COLUMNS = [
    "turn_uuid", "ts", "message", "intent", "quadrant", "valence", "arousal",
    "intensity", "strategy", "prompt_version", "anchor_version", "model", "reply",
    "self_quadrant", "gate_passed", "n_attempts", "voice_id", "rate", "volume",
    "pitch", "engine", "audio_path", "judge_id", "judge_level", "llm_temperature",
]


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
    # G6: the deciding judge, its independence level and the sampling temperature.
    # Defaults keep existing callers working.
    judge_id: str = ""
    judge_level: int = -1
    llm_temperature: float | None = None

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
        self._migrate()
        self._conn.commit()

    def _migrate(self) -> None:
        """Add newer columns to pre-existing turns and attempts tables (no-op if present)."""
        existing = {row[1] for row in self._conn.execute("PRAGMA table_info(turns)")}
        for col in ("volume", "pitch", "llm_temperature"):
            if col not in existing:
                self._conn.execute(f"ALTER TABLE turns ADD COLUMN {col} REAL")
        if "judge_id" not in existing:
            self._conn.execute("ALTER TABLE turns ADD COLUMN judge_id TEXT")
        if "judge_level" not in existing:
            self._conn.execute("ALTER TABLE turns ADD COLUMN judge_level INTEGER")
        att = {row[1] for row in self._conn.execute("PRAGMA table_info(attempts)")}
        if "judged_by" not in att:
            self._conn.execute("ALTER TABLE attempts ADD COLUMN judged_by TEXT")
        if "judge_level" not in att:
            self._conn.execute("ALTER TABLE attempts ADD COLUMN judge_level INTEGER")

    def save_turn(self, rec: TurnRecord) -> str:
        c = rec.contract
        accepted = rec.accepted
        vp = rec.voice_params
        values = (
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
            vp.voice_id,
            vp.rate,
            vp.volume,
            vp.pitch,
            rec.engine,
            rec.audio_path,
            rec.judge_id,
            rec.judge_level,
            rec.llm_temperature,
        )
        placeholders = ",".join("?" * len(_TURN_COLUMNS))
        with self._conn:  # transaction: commit on success, rollback on error
            self._conn.execute(
                f"INSERT INTO turns ({', '.join(_TURN_COLUMNS)}) VALUES ({placeholders})",
                values,
            )
            self._conn.executemany(
                "INSERT INTO attempts "
                "(turn_uuid, attempt_index, reply, self_quadrant, passed, accepted, raw, "
                "judged_by, judge_level) "
                "VALUES (?,?,?,?,?,?,?,?,?)",
                [
                    (
                        c.turn_uuid,
                        a.index,
                        a.reply,
                        a.self_quadrant.value if a.self_quadrant else None,
                        int(a.passed),
                        int(a.accepted),
                        a.raw,
                        a.judged_by,
                        a.judge_level,
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
