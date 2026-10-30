"""SQLite-backed append-only event store for OWNERA domain aggregates.

The store provides durable events, optimistic concurrency, idempotency keys and
per-aggregate hash-chain verification. Domain services remain responsible for
validating business transitions before appending events.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4


class EventStoreError(RuntimeError):
    """Base class for event-store failures."""


class ConcurrencyError(EventStoreError):
    """Raised when an aggregate version differs from the expected version."""


class IdempotencyConflict(EventStoreError):
    """Raised when an idempotency key is reused for different event content."""


class IntegrityError(EventStoreError):
    """Raised when stored event history fails hash-chain verification."""


@dataclass(frozen=True)
class StoredEvent:
    event_id: UUID
    aggregate_type: str
    aggregate_id: str
    version: int
    event_type: str
    payload: dict[str, Any]
    occurred_at: datetime
    idempotency_key: str | None
    previous_hash: str
    event_hash: str


class SQLiteEventStore:
    """Small durable event store using only the Python standard library."""

    GENESIS_HASH = "0" * 64

    def __init__(self, database_path: str | Path) -> None:
        self.database_path = str(database_path)
        if self.database_path == ":memory:":
            raise ValueError("use a file-backed SQLite database for durable event storage")
        Path(self.database_path).parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(
            self.database_path,
            timeout=10,
            isolation_level=None,
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 10000")
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA synchronous = FULL")
        return connection

    def _initialize(self) -> None:
        connection = self._connect()
        try:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS ownera_events (
                    event_id TEXT PRIMARY KEY,
                    aggregate_type TEXT NOT NULL,
                    aggregate_id TEXT NOT NULL,
                    version INTEGER NOT NULL CHECK(version > 0),
                    event_type TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    occurred_at TEXT NOT NULL,
                    idempotency_key TEXT UNIQUE,
                    previous_hash TEXT NOT NULL,
                    event_hash TEXT NOT NULL,
                    UNIQUE(aggregate_type, aggregate_id, version)
                )
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_ownera_events_aggregate
                ON ownera_events(aggregate_type, aggregate_id, version)
                """
            )
        finally:
            connection.close()

    def append(
        self,
        *,
        aggregate_type: str,
        aggregate_id: str,
        event_type: str,
        payload: dict[str, Any],
        expected_version: int,
        idempotency_key: str | None = None,
        occurred_at: datetime | None = None,
    ) -> StoredEvent:
        if not aggregate_type.strip() or not aggregate_id.strip():
            raise ValueError("aggregate_type and aggregate_id are required")
        if not event_type.strip():
            raise ValueError("event_type is required")
        if expected_version < 0:
            raise ValueError("expected_version cannot be negative")
        if idempotency_key is not None and not idempotency_key.strip():
            raise ValueError("idempotency_key cannot be empty")

        timestamp = occurred_at or datetime.now(timezone.utc)
        if timestamp.tzinfo is None:
            raise ValueError("occurred_at must be timezone-aware")
        timestamp_text = timestamp.astimezone(timezone.utc).isoformat()
        payload_text = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )

        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            if idempotency_key is not None:
                existing = connection.execute(
                    "SELECT * FROM ownera_events WHERE idempotency_key = ?",
                    (idempotency_key,),
                ).fetchone()
                if existing is not None:
                    same_request = (
                        existing["aggregate_type"] == aggregate_type
                        and existing["aggregate_id"] == aggregate_id
                        and existing["event_type"] == event_type
                        and existing["payload_json"] == payload_text
                    )
                    if not same_request:
                        raise IdempotencyConflict(
                            "idempotency key was used for different event content"
                        )
                    connection.commit()
                    return self._to_event(existing)

            latest = connection.execute(
                """
                SELECT version, event_hash FROM ownera_events
                WHERE aggregate_type = ? AND aggregate_id = ?
                ORDER BY version DESC LIMIT 1
                """,
                (aggregate_type, aggregate_id),
            ).fetchone()
            current_version = latest["version"] if latest else 0
            if current_version != expected_version:
                raise ConcurrencyError(
                    f"expected version {expected_version}, found {current_version}"
                )

            version = current_version + 1
            previous_hash = latest["event_hash"] if latest else self.GENESIS_HASH
            event_id = uuid4()
            hash_input = {
                "event_id": str(event_id),
                "aggregate_type": aggregate_type,
                "aggregate_id": aggregate_id,
                "version": version,
                "event_type": event_type,
                "payload_json": payload_text,
                "occurred_at": timestamp_text,
                "idempotency_key": idempotency_key,
                "previous_hash": previous_hash,
            }
            canonical = json.dumps(
                hash_input,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
            ).encode("utf-8")
            event_hash = hashlib.sha256(canonical).hexdigest()
            connection.execute(
                """
                INSERT INTO ownera_events (
                    event_id, aggregate_type, aggregate_id, version, event_type,
                    payload_json, occurred_at, idempotency_key, previous_hash, event_hash
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(event_id),
                    aggregate_type,
                    aggregate_id,
                    version,
                    event_type,
                    payload_text,
                    timestamp_text,
                    idempotency_key,
                    previous_hash,
                    event_hash,
                ),
            )
            connection.commit()
            return StoredEvent(
                event_id=event_id,
                aggregate_type=aggregate_type,
                aggregate_id=aggregate_id,
                version=version,
                event_type=event_type,
                payload=json.loads(payload_text),
                occurred_at=datetime.fromisoformat(timestamp_text),
                idempotency_key=idempotency_key,
                previous_hash=previous_hash,
                event_hash=event_hash,
            )
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def append_in_transaction(
        self,
        connection: sqlite3.Connection,
        *,
        aggregate_type: str,
        aggregate_id: str,
        event_type: str,
        payload: dict[str, Any],
        expected_version: int,
        idempotency_key: str | None = None,
        occurred_at: datetime | None = None,
    ) -> StoredEvent:
        """Append an event using a caller-owned SQLite transaction.

        The caller must have started a transaction on a connection to the same
        database and must commit or roll back both the event and its domain write.
        This method never commits or closes the connection.
        """
        if not aggregate_type.strip() or not aggregate_id.strip():
            raise ValueError("aggregate_type and aggregate_id are required")
        if not event_type.strip():
            raise ValueError("event_type is required")
        if expected_version < 0:
            raise ValueError("expected_version cannot be negative")
        if idempotency_key is not None and not idempotency_key.strip():
            raise ValueError("idempotency_key cannot be empty")
        timestamp = occurred_at or datetime.now(timezone.utc)
        if timestamp.tzinfo is None:
            raise ValueError("occurred_at must be timezone-aware")
        timestamp_text = timestamp.astimezone(timezone.utc).isoformat()
        payload_text = json.dumps(
            payload, sort_keys=True, separators=(",", ":"),
            ensure_ascii=False, allow_nan=False,
        )
        if idempotency_key is not None:
            existing = connection.execute(
                "SELECT * FROM ownera_events WHERE idempotency_key = ?",
                (idempotency_key,),
            ).fetchone()
            if existing is not None:
                same = (
                    existing["aggregate_type"] == aggregate_type
                    and existing["aggregate_id"] == aggregate_id
                    and existing["event_type"] == event_type
                    and existing["payload_json"] == payload_text
                )
                if not same:
                    raise IdempotencyConflict(
                        "idempotency key was used for different event content"
                    )
                return self._to_event(existing)
        latest = connection.execute(
            """SELECT version, event_hash FROM ownera_events
               WHERE aggregate_type = ? AND aggregate_id = ?
               ORDER BY version DESC LIMIT 1""",
            (aggregate_type, aggregate_id),
        ).fetchone()
        current_version = latest["version"] if latest else 0
        if current_version != expected_version:
            raise ConcurrencyError(
                f"expected version {expected_version}, found {current_version}"
            )
        version = current_version + 1
        previous_hash = latest["event_hash"] if latest else self.GENESIS_HASH
        event_id = uuid4()
        hash_input = {
            "event_id": str(event_id), "aggregate_type": aggregate_type,
            "aggregate_id": aggregate_id, "version": version,
            "event_type": event_type, "payload_json": payload_text,
            "occurred_at": timestamp_text, "idempotency_key": idempotency_key,
            "previous_hash": previous_hash,
        }
        canonical = json.dumps(
            hash_input, sort_keys=True, separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
        event_hash = hashlib.sha256(canonical).hexdigest()
        connection.execute(
            """INSERT INTO ownera_events (
                event_id, aggregate_type, aggregate_id, version, event_type,
                payload_json, occurred_at, idempotency_key, previous_hash, event_hash
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                str(event_id), aggregate_type, aggregate_id, version, event_type,
                payload_text, timestamp_text, idempotency_key, previous_hash, event_hash,
            ),
        )
        return StoredEvent(
            event_id=event_id, aggregate_type=aggregate_type,
            aggregate_id=aggregate_id, version=version, event_type=event_type,
            payload=json.loads(payload_text),
            occurred_at=datetime.fromisoformat(timestamp_text),
            idempotency_key=idempotency_key, previous_hash=previous_hash,
            event_hash=event_hash,
        )

    def load(
        self,
        aggregate_type: str,
        aggregate_id: str,
    ) -> tuple[StoredEvent, ...]:
        connection = self._connect()
        try:
            rows = connection.execute(
                """
                SELECT * FROM ownera_events
                WHERE aggregate_type = ? AND aggregate_id = ?
                ORDER BY version
                """,
                (aggregate_type, aggregate_id),
            ).fetchall()
        finally:
            connection.close()
        return tuple(self._to_event(row) for row in rows)

    def verify(self, aggregate_type: str, aggregate_id: str) -> bool:
        events = self.load(aggregate_type, aggregate_id)
        previous_hash = self.GENESIS_HASH
        for expected_version, event in enumerate(events, start=1):
            if event.version != expected_version:
                raise IntegrityError("event sequence contains a version gap")
            if event.previous_hash != previous_hash:
                raise IntegrityError("event hash chain predecessor mismatch")
            hash_input = {
                "event_id": str(event.event_id),
                "aggregate_type": event.aggregate_type,
                "aggregate_id": event.aggregate_id,
                "version": event.version,
                "event_type": event.event_type,
                "payload_json": json.dumps(
                    event.payload,
                    sort_keys=True,
                    separators=(",", ":"),
                    ensure_ascii=False,
                    allow_nan=False,
                ),
                "occurred_at": event.occurred_at.astimezone(timezone.utc).isoformat(),
                "idempotency_key": event.idempotency_key,
                "previous_hash": event.previous_hash,
            }
            canonical = json.dumps(
                hash_input,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
            ).encode("utf-8")
            calculated = hashlib.sha256(canonical).hexdigest()
            if calculated != event.event_hash:
                raise IntegrityError("event hash mismatch")
            previous_hash = event.event_hash
        return True

    @staticmethod
    def _to_event(row: sqlite3.Row) -> StoredEvent:
        return StoredEvent(
            event_id=UUID(row["event_id"]),
            aggregate_type=row["aggregate_type"],
            aggregate_id=row["aggregate_id"],
            version=row["version"],
            event_type=row["event_type"],
            payload=json.loads(row["payload_json"]),
            occurred_at=datetime.fromisoformat(row["occurred_at"]),
            idempotency_key=row["idempotency_key"],
            previous_hash=row["previous_hash"],
            event_hash=row["event_hash"],
        )
