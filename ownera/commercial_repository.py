"""Versioned, integrity-checked SQLite persistence for the commercial pipeline."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ownera.commercial import CommercialEngine


class CommercialRepositoryError(RuntimeError):
    """Base commercial persistence error."""


class CommercialSnapshotConflict(CommercialRepositoryError):
    """A writer attempted to overwrite a newer commercial snapshot."""


class CommercialSnapshotIntegrityError(CommercialRepositoryError):
    """Persisted commercial snapshot digest does not match its payload."""


@dataclass(frozen=True)
class CommercialSnapshot:
    version: int
    engine: CommercialEngine
    digest: str


class SQLiteCommercialRepository:
    """Stores the complete commercial state in one optimistic SQLite snapshot."""

    SNAPSHOT_ID = "primary"

    def __init__(self, database_path: str | Path) -> None:
        self.database_path = str(database_path)
        if self.database_path == ":memory:":
            raise ValueError("commercial persistence requires a file-backed database")
        Path(self.database_path).parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS commercial_snapshots (
                    snapshot_id TEXT PRIMARY KEY,
                    version INTEGER NOT NULL CHECK(version > 0),
                    payload_json TEXT NOT NULL,
                    digest TEXT NOT NULL
                )
                """
            )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=10, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout = 10000")
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA synchronous = FULL")
        return connection

    def save(self, engine: CommercialEngine, *, expected_version: int) -> int:
        if expected_version < 0:
            raise ValueError("expected_version cannot be negative")
        payload = json.dumps(
            engine.to_snapshot(), sort_keys=True, separators=(",", ":"),
            ensure_ascii=False, allow_nan=False,
        )
        digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT version FROM commercial_snapshots WHERE snapshot_id = ?",
                (self.SNAPSHOT_ID,),
            ).fetchone()
            current = row["version"] if row else 0
            if current != expected_version:
                raise CommercialSnapshotConflict(
                    f"expected commercial version {expected_version}, found {current}"
                )
            next_version = current + 1
            connection.execute(
                """
                INSERT INTO commercial_snapshots(snapshot_id, version, payload_json, digest)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(snapshot_id) DO UPDATE SET
                    version=excluded.version, payload_json=excluded.payload_json,
                    digest=excluded.digest
                """,
                (self.SNAPSHOT_ID, next_version, payload, digest),
            )
            connection.commit()
            return next_version
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def load(self) -> CommercialSnapshot | None:
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT version, payload_json, digest FROM commercial_snapshots WHERE snapshot_id = ?",
                (self.SNAPSHOT_ID,),
            ).fetchone()
        finally:
            connection.close()
        if row is None:
            return None
        actual = hashlib.sha256(row["payload_json"].encode("utf-8")).hexdigest()
        if actual != row["digest"]:
            raise CommercialSnapshotIntegrityError("commercial snapshot digest mismatch")
        try:
            payload: dict[str, Any] = json.loads(row["payload_json"])
            engine = CommercialEngine.from_snapshot(payload)
        except (KeyError, TypeError, ValueError) as exc:
            raise CommercialRepositoryError("commercial snapshot payload is invalid") from exc
        return CommercialSnapshot(row["version"], engine, row["digest"])
