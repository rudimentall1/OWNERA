"""Automatically persisted facade for OWNERA workforce state transitions."""

from __future__ import annotations

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
from ownera.workforce_repository import SQLiteWorkforceRepository


class PersistentWorkforce:
    """Persists each accepted workforce command before returning success.

    A stale writer reloads the last committed snapshot and raises the repository
    conflict. This is a single-snapshot SQLite design, not a distributed queue.
    """

    def __init__(self, database_path: str | Path) -> None:
        self.repository = SQLiteWorkforceRepository(database_path)
        snapshot = self.repository.load()
        if snapshot is None:
            self._engine = WorkforceEngine()
            self._version = self.repository.save(self._engine, expected_version=0)
        else:
            self._engine = snapshot.engine
            self._version = snapshot.version

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

    def register_worker(self, worker: WorkerProfile) -> None:
        self._execute(lambda: self._engine.register_worker(worker))

    def add_task(self, task: WorkTask) -> None:
        self.add_tasks((task,))

    def add_tasks(self, tasks: tuple[WorkTask, ...]) -> None:
        self._execute(lambda: self._engine.add_tasks(tasks))

    def assign(self, task_id: UUID) -> WorkTask:
        return self._execute(lambda: self._engine.assign(task_id))

    def start(self, task_id: UUID, worker_id: str) -> WorkTask:
        return self._execute(lambda: self._engine.start(task_id, worker_id))

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
            )
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
            )
        )

    def refresh(self) -> None:
        """Reload the latest committed state from the repository."""
        snapshot = self.repository.load()
        if snapshot is None:
            raise RuntimeError("workforce snapshot unexpectedly missing")
        self._engine = snapshot.engine
        self._version = snapshot.version

    def _execute(self, command):
        try:
            result = command()
            self._version = self.repository.save(
                self._engine,
                expected_version=self._version,
            )
            return result
        except Exception:
            # The in-memory engine may have changed before a persistence error.
            # Discard it and restore the last committed snapshot.
            snapshot = self.repository.load()
            if snapshot is not None:
                self._engine = snapshot.engine
                self._version = snapshot.version
            raise
