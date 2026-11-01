"""Local execution bridge for an already-started NEAR marketplace assignment.

Marketplace-specific start/submit calls are deliberately kept out of this module
until their authenticated API contract is verified. A trusted planner supplies
an explicit sandbox command and acceptance contract; marketplace text is never
executed as a shell command.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from ownera.artifact_registry import SQLiteArtifactRegistry
from ownera.persistent_workforce import PersistentWorkforce
from ownera.worker_execution import WorkerExecutionService, WorkerSubmission
from ownera.worker_runtime import WorkerExecutionRequest
from ownera.workforce import TaskStatus, WorkerProfile, WorkTask


@dataclass(frozen=True)
class AssignmentExecutionSpec:
    assignment_id: str
    job_id: str
    status: str
    title: str
    description: str
    budget: Decimal
    currency: str
    required_capabilities: frozenset[str]
    acceptance_criteria: tuple[str, ...]
    request: WorkerExecutionRequest
    summary: str
    actual_cost: Decimal = Decimal("0")

    def __post_init__(self) -> None:
        for name in ("assignment_id", "job_id", "title", "description", "currency", "summary"):
            if not getattr(self, name).strip():
                raise ValueError(f"{name} is required")
        if self.status.casefold() not in {"started", "in_progress"}:
            raise ValueError("marketplace assignment must already be started")
        if not self.required_capabilities or not self.acceptance_criteria:
            raise ValueError("capabilities and acceptance criteria are required")
        if self.request.task_id != str(uuid5(NAMESPACE_URL, f"ownera-near-assignment:{self.assignment_id}")):
            raise ValueError("execution request task_id does not match deterministic assignment task id")
        if self.budget < 0 or self.actual_cost < 0 or self.actual_cost > self.budget:
            raise ValueError("execution cost must be non-negative and within assignment budget")


def dispatch_started_assignment(
    spec: AssignmentExecutionSpec,
    *,
    database_path: str | Path,
    worker: WorkerProfile,
    runtime,
) -> WorkerSubmission:
    """Create, start, execute and locally submit one started assignment.

    Safe to call once per assignment. Existing non-IN_PROGRESS tasks are never
    executed again. A task left IN_PROGRESS after a crash requires reconciliation.
    """
    task_id = uuid5(NAMESPACE_URL, f"ownera-near-assignment:{spec.assignment_id}")
    workforce = PersistentWorkforce(database_path)
    existing = next((task for task in workforce.tasks if task.task_id == task_id), None)
    registered = next((item for item in workforce.workers if item.worker_id == worker.worker_id), None)
    if registered is not None and registered != worker:
        raise RuntimeError("registered worker profile differs from requested execution profile")
    if existing is not None:
        if existing.status is not TaskStatus.IN_PROGRESS:
            raise RuntimeError(f"assignment already processed locally with status {existing.status.value}")
        if existing.assigned_worker_id != worker.worker_id:
            raise RuntimeError("assignment is already owned by a different worker")

    db = sqlite3.connect(str(database_path), timeout=10)
    try:
        db.execute("""CREATE TABLE IF NOT EXISTS near_market_execution_claims (
            assignment_id TEXT PRIMARY KEY,
            task_id TEXT NOT NULL,
            state TEXT NOT NULL CHECK(state IN ('RUNNING', 'COMPLETED')),
            claimed_at TEXT NOT NULL,
            completed_at TEXT
        )""")
        try:
            db.execute(
                "INSERT INTO near_market_execution_claims VALUES (?, ?, 'RUNNING', ?, NULL)",
                (spec.assignment_id, str(task_id), datetime.now(timezone.utc).isoformat()),
            )
            db.commit()
        except sqlite3.IntegrityError as exc:
            raise RuntimeError("assignment already has an execution claim; reconcile before retry") from exc
    finally:
        db.close()

    if existing is None:
        if registered is None:
            workforce.register_worker(worker)
        task = WorkTask(
            task_id=task_id,
            title=spec.title,
            description=spec.description,
            required_capabilities=spec.required_capabilities,
            budget_limit=spec.budget,
            currency=spec.currency,
            acceptance_criteria=spec.acceptance_criteria,
        )
        workforce.add_task(task)
        workforce.assign(task_id)
        workforce.start(task_id, worker.worker_id)

    service = WorkerExecutionService(
        runtime=runtime,
        registry=SQLiteArtifactRegistry(database_path),
        workforce=workforce,
    )
    submission = service.execute_and_submit(
        spec.request,
        worker_id=worker.worker_id,
        summary=spec.summary,
        actual_cost=spec.actual_cost,
    )
    db = sqlite3.connect(str(database_path), timeout=10)
    try:
        db.execute(
            "UPDATE near_market_execution_claims SET state='COMPLETED', completed_at=? WHERE assignment_id=? AND state='RUNNING'",
            (datetime.now(timezone.utc).isoformat(), spec.assignment_id),
        )
        db.commit()
    finally:
        db.close()
    return submission
