"""Durable SQLite snapshots for the deterministic OWNERA workforce engine."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID
from typing import Any

from ownera.workforce import WorkforceEngine


class WorkforceRepositoryError(RuntimeError):
    """Base class for workforce repository errors."""


class SnapshotConflict(WorkforceRepositoryError):
    """Raised when a snapshot is saved against a stale repository version."""


class SnapshotIntegrityError(WorkforceRepositoryError):
    """Raised when persisted snapshot bytes do not match their digest."""


@dataclass(frozen=True)
class WorkforceSnapshot:
    version: int
    engine: WorkforceEngine
    digest: str


@dataclass(frozen=True)
class PersistedOrderHandoff:
    order_id: UUID
    proposal_id: UUID
    task_ids: tuple[UUID, ...]
    converted_at: str
    plan_digest: str
    snapshot_version: int
    created: bool


class SQLiteWorkforceRepository:
    """Stores one complete workforce snapshot with optimistic version checks."""

    SNAPSHOT_ID = "primary"

    def __init__(self, database_path: str | Path) -> None:
        self.database_path = str(database_path)
        if self.database_path == ":memory:":
            raise ValueError("workforce snapshots require a file-backed database")
        Path(self.database_path).parent.mkdir(parents=True, exist_ok=True)
        connection = self._connect()
        try:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS workforce_snapshots (
                    snapshot_id TEXT PRIMARY KEY,
                    version INTEGER NOT NULL CHECK(version > 0),
                    payload_json TEXT NOT NULL,
                    digest TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS order_handoffs (
                    order_id TEXT PRIMARY KEY,
                    proposal_id TEXT NOT NULL,
                    task_ids_json TEXT NOT NULL,
                    converted_at TEXT NOT NULL,
                    plan_digest TEXT NOT NULL,
                    snapshot_version INTEGER NOT NULL
                )
                """
            )
        finally:
            connection.close()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(
            self.database_path,
            timeout=10,
            isolation_level=None,
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout = 10000")
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA synchronous = FULL")
        return connection

    def save(self, engine: WorkforceEngine, *, expected_version: int) -> int:
        if expected_version < 0:
            raise ValueError("expected_version cannot be negative")
        payload_json = json.dumps(
            engine.to_snapshot(),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
        digest = hashlib.sha256(payload_json.encode("utf-8")).hexdigest()
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT version FROM workforce_snapshots WHERE snapshot_id = ?",
                (self.SNAPSHOT_ID,),
            ).fetchone()
            current_version = row["version"] if row else 0
            if current_version != expected_version:
                raise SnapshotConflict(
                    f"expected snapshot version {expected_version}, found {current_version}"
                )
            next_version = current_version + 1
            connection.execute(
                """
                INSERT INTO workforce_snapshots (
                    snapshot_id, version, payload_json, digest
                ) VALUES (?, ?, ?, ?)
                ON CONFLICT(snapshot_id) DO UPDATE SET
                    version = excluded.version,
                    payload_json = excluded.payload_json,
                    digest = excluded.digest
                """,
                (self.SNAPSHOT_ID, next_version, payload_json, digest),
            )
            connection.commit()
            return next_version
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()


    def save_with_order_handoff(
        self,
        engine: WorkforceEngine,
        *,
        expected_version: int,
        order_id: UUID,
        proposal_id: UUID,
        task_ids: tuple[UUID, ...],
        converted_at: str,
        plan_digest: str,
    ) -> PersistedOrderHandoff:
        """Commit workforce snapshot and order idempotency record atomically."""
        if expected_version < 0:
            raise ValueError("expected_version cannot be negative")
        if not task_ids:
            raise ValueError("at least one task ID is required")
        payload_json = json.dumps(
            engine.to_snapshot(),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
        digest = hashlib.sha256(payload_json.encode("utf-8")).hexdigest()
        task_ids_json = json.dumps([str(item) for item in task_ids])
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                "SELECT * FROM order_handoffs WHERE order_id = ?",
                (str(order_id),),
            ).fetchone()
            if existing is not None:
                same_request = (
                    existing["proposal_id"] == str(proposal_id)
                    and existing["plan_digest"] == plan_digest
                )
                if not same_request:
                    raise SnapshotConflict(
                        "order ID was already committed with different proposal or task plan"
                    )
                connection.commit()
                return PersistedOrderHandoff(
                    order_id=UUID(existing["order_id"]),
                    proposal_id=UUID(existing["proposal_id"]),
                    task_ids=tuple(
                        UUID(item) for item in json.loads(existing["task_ids_json"])
                    ),
                    converted_at=existing["converted_at"],
                    plan_digest=existing["plan_digest"],
                    snapshot_version=existing["snapshot_version"],
                    created=False,
                )

            row = connection.execute(
                "SELECT version FROM workforce_snapshots WHERE snapshot_id = ?",
                (self.SNAPSHOT_ID,),
            ).fetchone()
            current_version = row["version"] if row else 0
            if current_version != expected_version:
                raise SnapshotConflict(
                    f"expected snapshot version {expected_version}, found {current_version}"
                )
            next_version = current_version + 1
            connection.execute(
                """
                INSERT INTO workforce_snapshots (
                    snapshot_id, version, payload_json, digest
                ) VALUES (?, ?, ?, ?)
                ON CONFLICT(snapshot_id) DO UPDATE SET
                    version = excluded.version,
                    payload_json = excluded.payload_json,
                    digest = excluded.digest
                """,
                (self.SNAPSHOT_ID, next_version, payload_json, digest),
            )
            connection.execute(
                """
                INSERT INTO order_handoffs (
                    order_id, proposal_id, task_ids_json, converted_at,
                    plan_digest, snapshot_version
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    str(order_id),
                    str(proposal_id),
                    task_ids_json,
                    converted_at,
                    plan_digest,
                    next_version,
                ),
            )
            connection.commit()
            return PersistedOrderHandoff(
                order_id=order_id,
                proposal_id=proposal_id,
                task_ids=task_ids,
                converted_at=converted_at,
                plan_digest=plan_digest,
                snapshot_version=next_version,
                created=True,
            )
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def load(self) -> WorkforceSnapshot | None:
        connection = self._connect()
        try:
            row = connection.execute(
                """
                SELECT version, payload_json, digest
                FROM workforce_snapshots WHERE snapshot_id = ?
                """,
                (self.SNAPSHOT_ID,),
            ).fetchone()
        finally:
            connection.close()
        if row is None:
            return None
        actual_digest = hashlib.sha256(row["payload_json"].encode("utf-8")).hexdigest()
        if actual_digest != row["digest"]:
            raise SnapshotIntegrityError("workforce snapshot digest mismatch")
        try:
            payload: dict[str, Any] = json.loads(row["payload_json"])
            engine = WorkforceEngine.from_snapshot(payload)
        except (KeyError, TypeError, ValueError) as exc:
            raise WorkforceRepositoryError("workforce snapshot payload is invalid") from exc
        return WorkforceSnapshot(
            version=row["version"],
            engine=engine,
            digest=row["digest"],
        )
