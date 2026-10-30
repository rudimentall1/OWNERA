"""Durable SQLite snapshots for the deterministic OWNERA workforce engine."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import UUID

from ownera.event_store import SQLiteEventStore, StoredEvent
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
    evidence_digest: str
    created: bool


class SQLiteWorkforceRepository:
    """Stores one complete workforce snapshot with optimistic version checks."""

    SNAPSHOT_ID = "primary"

    def __init__(self, database_path: str | Path) -> None:
        self.database_path = str(database_path)
        if self.database_path == ":memory:":
            raise ValueError("workforce snapshots require a file-backed database")
        Path(self.database_path).parent.mkdir(parents=True, exist_ok=True)
        self.event_store = SQLiteEventStore(database_path)
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
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS order_acceptance_evidence (
                    order_id TEXT PRIMARY KEY,
                    evidence_json TEXT NOT NULL,
                    evidence_digest TEXT NOT NULL,
                    recorded_at TEXT NOT NULL,
                    FOREIGN KEY(order_id) REFERENCES order_handoffs(order_id)
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


    def save_with_event(
        self,
        engine: WorkforceEngine,
        *,
        expected_version: int,
        expected_event_version: int,
        event_type: str,
        payload: dict[str, Any],
        idempotency_key: str,
    ) -> tuple[int, StoredEvent]:
        """Commit the workforce snapshot and its lifecycle event atomically."""
        if expected_version < 0 or expected_event_version < 0:
            raise ValueError("expected versions cannot be negative")
        payload_json = json.dumps(
            engine.to_snapshot(), sort_keys=True, separators=(",", ":"),
            ensure_ascii=False, allow_nan=False,
        )
        digest = hashlib.sha256(payload_json.encode("utf-8")).hexdigest()
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT version FROM workforce_snapshots WHERE snapshot_id = ?",
                (self.SNAPSHOT_ID,),
            ).fetchone()
            current = row["version"] if row else 0
            if current != expected_version:
                raise SnapshotConflict(
                    f"expected snapshot version {expected_version}, found {current}"
                )
            event = self.event_store.append_in_transaction(
                connection,
                aggregate_type="workforce",
                aggregate_id=self.SNAPSHOT_ID,
                event_type=event_type,
                payload=payload,
                expected_version=expected_event_version,
                idempotency_key=idempotency_key,
            )
            next_version = current + 1
            connection.execute(
                """INSERT INTO workforce_snapshots(
                    snapshot_id, version, payload_json, digest
                ) VALUES (?, ?, ?, ?)
                ON CONFLICT(snapshot_id) DO UPDATE SET
                    version=excluded.version, payload_json=excluded.payload_json,
                    digest=excluded.digest""",
                (self.SNAPSHOT_ID, next_version, payload_json, digest),
            )
            connection.commit()
            return next_version, event
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
        expected_event_version: int,
        order_id: UUID,
        proposal_id: UUID,
        task_ids: tuple[UUID, ...],
        converted_at: str,
        plan_digest: str,
        acceptance_evidence: dict[str, Any],
    ) -> PersistedOrderHandoff:
        """Commit snapshot, acceptance evidence, handoff record, and event atomically."""
        if expected_version < 0 or expected_event_version < 0:
            raise ValueError("expected versions cannot be negative")
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
        evidence_json = json.dumps(
            acceptance_evidence, sort_keys=True, separators=(",", ":"),
            ensure_ascii=False, allow_nan=False,
        )
        evidence_digest = hashlib.sha256(evidence_json.encode("utf-8")).hexdigest()
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                "SELECT * FROM order_handoffs WHERE order_id = ?",
                (str(order_id),),
            ).fetchone()
            if existing is not None:
                evidence_row = connection.execute(
                    "SELECT evidence_digest FROM order_acceptance_evidence WHERE order_id = ?",
                    (str(order_id),),
                ).fetchone()
                same_request = (
                    existing["proposal_id"] == str(proposal_id)
                    and existing["plan_digest"] == plan_digest
                    and evidence_row is not None
                    and evidence_row["evidence_digest"] == evidence_digest
                )
                if not same_request:
                    raise SnapshotConflict(
                        "order ID was already committed with different proposal, task plan, or acceptance evidence"
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
                    evidence_digest=evidence_digest,
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
            self.event_store.append_in_transaction(
                connection,
                aggregate_type="workforce",
                aggregate_id=self.SNAPSHOT_ID,
                event_type="OrderTasksHandedOff",
                payload={
                    "order_id": str(order_id),
                    "proposal_id": str(proposal_id),
                    "task_ids": [str(item) for item in task_ids],
                    "converted_at": converted_at,
                    "plan_digest": plan_digest,
                    "acceptance_evidence_digest": evidence_digest,
                },
                expected_version=expected_event_version,
                idempotency_key=f"OrderTasksHandedOff:{order_id}:{plan_digest}",
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
            connection.execute(
                """
                INSERT INTO order_acceptance_evidence (
                    order_id, evidence_json, evidence_digest, recorded_at
                ) VALUES (?, ?, ?, ?)
                """,
                (
                    str(order_id), evidence_json, evidence_digest, converted_at,
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
                evidence_digest=evidence_digest,
                created=True,
            )
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def load_order_acceptance_evidence(self, order_id: UUID) -> dict[str, Any]:
        """Load and integrity-check the immutable acceptance evidence for an order."""
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT evidence_json, evidence_digest FROM order_acceptance_evidence WHERE order_id = ?",
                (str(order_id),),
            ).fetchone()
            if row is None:
                raise KeyError(f"acceptance evidence not found for order {order_id}")
            actual = hashlib.sha256(row["evidence_json"].encode("utf-8")).hexdigest()
            if actual != row["evidence_digest"]:
                raise SnapshotIntegrityError(
                    f"acceptance evidence digest mismatch for order {order_id}"
                )
            self.event_store.verify("workforce", self.SNAPSHOT_ID)
            matching_events = [
                event for event in self.event_store.load("workforce", self.SNAPSHOT_ID)
                if event.event_type == "OrderTasksHandedOff"
                and event.payload.get("order_id") == str(order_id)
            ]
            if len(matching_events) != 1 or (
                matching_events[0].payload.get("acceptance_evidence_digest")
                != row["evidence_digest"]
            ):
                raise SnapshotIntegrityError(
                    f"acceptance evidence is not bound to the order handoff event for {order_id}"
                )
            return json.loads(row["evidence_json"])
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
