"""Verified bridge from isolated worker execution to persistent task submission."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol
from uuid import UUID

from ownera.artifact_registry import ArtifactRecord, SQLiteArtifactRegistry
from ownera.persistent_workforce import PersistentWorkforce
from ownera.worker_runtime import WorkerExecutionRequest, WorkerExecutionResult


class RuntimeExecutor(Protocol):
    def execute(self, request: WorkerExecutionRequest) -> WorkerExecutionResult: ...


class WorkerExecutionFailed(RuntimeError):
    """Execution did not produce a submit-ready result."""


@dataclass(frozen=True)
class WorkerSubmission:
    task_id: UUID
    worker_id: str
    runtime_status: str
    artifact_records: tuple[ArtifactRecord, ...]
    artifact_refs: tuple[str, ...]
    workforce_version: int


class WorkerExecutionService:
    """Execute an already-started task, register outputs, then submit digest refs.

    This service does not assign or start tasks, approve work, or spend funds.
    The caller remains responsible for starting a task through PersistentWorkforce.
    """

    def __init__(
        self,
        *,
        runtime: RuntimeExecutor,
        registry: SQLiteArtifactRegistry,
        workforce: PersistentWorkforce,
    ) -> None:
        self.runtime = runtime
        self.registry = registry
        self.workforce = workforce

    def execute_and_submit(
        self,
        request: WorkerExecutionRequest,
        *,
        worker_id: str,
        summary: str,
        actual_cost: Decimal,
    ) -> WorkerSubmission:
        if not worker_id or not worker_id.strip():
            raise ValueError("worker_id is required")
        if not summary or not summary.strip():
            raise ValueError("summary is required")
        if actual_cost < 0:
            raise ValueError("actual_cost cannot be negative")

        task = self._find_task(request.task_id)
        if task.status.value != "IN_PROGRESS":
            raise WorkerExecutionFailed("task must be IN_PROGRESS before runtime execution")
        if task.assigned_worker_id != worker_id:
            raise WorkerExecutionFailed("only the assigned worker may execute this task")

        result = self.runtime.execute(request)
        if result.task_id != request.task_id:
            raise WorkerExecutionFailed("runtime returned a result for a different task")
        if result.status != "SUCCEEDED" or result.exit_code != 0:
            raise WorkerExecutionFailed(
                f"worker execution did not succeed (status={result.status}, exit_code={result.exit_code})"
            )
        if not result.artifacts:
            raise WorkerExecutionFailed("successful execution produced no registered artifacts")

        records: list[ArtifactRecord] = []
        refs: list[str] = []
        for path, data in sorted(result.artifacts.items()):
            # Preserve the container-relative path in a reversible metadata-safe form.
            logical_name = path.replace("/", "__")
            record = self.registry.put(
                task_id=request.task_id,
                worker_id=worker_id,
                artifact_name=logical_name,
                content=data,
            )
            records.append(record)
            refs.append(f"sha256:{record.sha256}")

        submitted = self.workforce.submit(
            task.task_id,
            worker_id,
            summary=summary,
            artifact_refs=tuple(refs),
            actual_cost=actual_cost,
        )
        return WorkerSubmission(
            task_id=task.task_id,
            worker_id=worker_id,
            runtime_status=result.status,
            artifact_records=tuple(records),
            artifact_refs=tuple(refs),
            workforce_version=self.workforce.version,
        )

    def _find_task(self, task_id: str):
        for task in self.workforce.tasks:
            if str(task.task_id) == task_id:
                return task
        raise WorkerExecutionFailed(f"unknown workforce task: {task_id}")
