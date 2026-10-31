"""Automatically persisted facade for OWNERA workforce state transitions."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from uuid import UUID

from ownera.workforce import (
    TaskReview,
    WorkerProfile,
    WorkforceEngine,
    WorkTask,
)
from ownera.workforce_repository import (
    PersistedOrderHandoff,
    SQLiteWorkforceRepository,
)


class PersistentWorkforce:
    """Persists each successful workforce transition with a hash-chained event."""

    AGGREGATE_ID = "primary"

    def __init__(self, database_path: str | Path) -> None:
        self.repository = SQLiteWorkforceRepository(database_path)
        snapshot = self.repository.load()
        if snapshot is None:
            self._engine = WorkforceEngine()
            self._version = self.repository.save(self._engine, expected_version=0)
        else:
            self._engine = snapshot.engine
            self._version = snapshot.version
        self.repository.event_store.verify("workforce", self.AGGREGATE_ID)
        self._event_version = len(
            self.repository.event_store.load("workforce", self.AGGREGATE_ID)
        )

    @property
    def tasks(self) -> tuple[WorkTask, ...]:
        return self._engine.tasks

    @property
    def workers(self) -> tuple[WorkerProfile, ...]:
        return self._engine.workers

    @property
    def reviews(self) -> tuple[TaskReview, ...]:
        return self._engine.reviews

    @property
    def version(self) -> int:
        return self._version

    @property
    def event_version(self) -> int:
        return self._event_version

    def register_worker(self, worker: WorkerProfile) -> None:
        self._execute(
            lambda: self._engine.register_worker(worker),
            event_type="WorkerRegistered",
            payload={
                "worker_id": worker.worker_id,
                "role": worker.role,
                "capabilities": sorted(worker.capabilities),
                "max_concurrent_tasks": worker.max_concurrent_tasks,
                "enabled": worker.enabled,
            },
        )

    def add_task(self, task: WorkTask) -> None:
        self.add_tasks((task,))

    def add_tasks(self, tasks: tuple[WorkTask, ...]) -> None:
        self._execute(
            lambda: self._engine.add_tasks(tasks),
            event_type="TaskCreated",
            payload={
                "tasks": [
                    {
                        "task_id": str(task.task_id),
                        "title": task.title,
                        "required_capabilities": sorted(task.required_capabilities),
                        "budget_limit": str(task.budget_limit),
                        "currency": task.currency,
                        "acceptance_criteria": list(task.acceptance_criteria),
                        "dependencies": [str(item) for item in task.dependencies],
                    }
                    for task in tasks
                ]
            },
        )

    def add_order_tasks(
        self,
        tasks: tuple[WorkTask, ...],
        *,
        order_id: UUID,
        proposal_id: UUID,
        converted_at: str,
        plan_digest: str,
        acceptance_evidence: dict,
    ) -> PersistedOrderHandoff:
        """Atomically persist a task graph and order idempotency record."""
        try:
            self._engine.add_tasks(tasks)
            record = self.repository.save_with_order_handoff(
                self._engine,
                expected_version=self._version,
                expected_event_version=self._event_version,
                order_id=order_id,
                proposal_id=proposal_id,
                task_ids=tuple(task.task_id for task in tasks),
                converted_at=converted_at,
                plan_digest=plan_digest,
                acceptance_evidence=acceptance_evidence,
            )
            if record.created:
                self._version = record.snapshot_version
                self._event_version += 1
            else:
                self.refresh()
            return record
        except Exception:
            self.refresh()
            raise

    def assign(self, task_id: UUID) -> WorkTask:
        return self._execute(
            lambda: self._engine.assign(task_id),
            event_type="TaskAssigned",
            payload={"task_id": str(task_id)},
        )

    def start(self, task_id: UUID, worker_id: str) -> WorkTask:
        return self._execute(
            lambda: self._engine.start(task_id, worker_id),
            event_type="TaskStarted",
            payload={"task_id": str(task_id), "worker_id": worker_id},
        )

    def submit(
        self,
        task_id: UUID,
        worker_id: str,
        *,
        summary: str,
        artifact_refs: tuple[str, ...],
        actual_cost: Decimal,
    ) -> WorkTask:
        return self._execute(
            lambda: self._engine.submit(
                task_id,
                worker_id,
                summary=summary,
                artifact_refs=artifact_refs,
                actual_cost=actual_cost,
            ),
            event_type="TaskSubmitted",
            payload={
                "task_id": str(task_id),
                "worker_id": worker_id,
                "actual_cost": str(actual_cost),
                "artifact_refs": list(artifact_refs),
                "result_summary": summary,
            },
        )

    def review(
        self,
        task_id: UUID,
        reviewer_id: str,
        *,
        accepted: bool,
        findings: tuple[str, ...] = (),
        now: datetime | None = None,
    ) -> WorkTask:
        return self._execute(
            lambda: self._engine.review(
                task_id,
                reviewer_id,
                accepted=accepted,
                findings=findings,
                now=now,
            ),
            event_type="TaskReviewAccepted" if accepted else "TaskReviewRejected",
            payload={
                "task_id": str(task_id),
                "reviewer_id": reviewer_id,
                "accepted": accepted,
                "findings": list(findings),
                "reviewed_at": (now.isoformat() if now else None),
            },
        )

    def refresh(self) -> None:
        """Reload committed state and verify its append-only event history."""
        snapshot = self.repository.load()
        if snapshot is None:
            raise RuntimeError("workforce snapshot unexpectedly missing")
        self.repository.event_store.verify("workforce", self.AGGREGATE_ID)
        self._engine = snapshot.engine
        self._version = snapshot.version
        self._event_version = len(
            self.repository.event_store.load("workforce", self.AGGREGATE_ID)
        )

    def _execute(self, command, *, event_type: str, payload: dict):
        try:
            result = command()
            canonical = json.dumps(
                payload, sort_keys=True, separators=(",", ":"),
                ensure_ascii=False, allow_nan=False,
            )
            digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
            self._version, event = self.repository.save_with_event(
                self._engine,
                expected_version=self._version,
                expected_event_version=self._event_version,
                event_type=event_type,
                payload=payload,
                idempotency_key=f"{event_type}:{self.AGGREGATE_ID}:v{self._version}:{digest}",
            )
            self._event_version = event.version
            return result
        except Exception:
            self.refresh()
            raise
