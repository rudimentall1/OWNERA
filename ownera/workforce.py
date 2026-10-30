"""Deterministic coordination core for OWNERA's agent workforce.

This module assigns bounded work to registered workers. It does not run LLMs,
execute tools, authorize external commitments, or move money. Execution adapters
must be isolated and all external actions remain behind OWNERA policy controls.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from uuid import UUID, uuid4


class WorkforceError(RuntimeError):
    """Raised when a workforce transition violates the task contract."""


class TaskStatus(str, Enum):
    PLANNED = "PLANNED"
    ASSIGNED = "ASSIGNED"
    IN_PROGRESS = "IN_PROGRESS"
    READY_FOR_REVIEW = "READY_FOR_REVIEW"
    REWORK_REQUIRED = "REWORK_REQUIRED"
    ACCEPTED = "ACCEPTED"


@dataclass(frozen=True)
class WorkerProfile:
    worker_id: str
    role: str
    capabilities: frozenset[str]
    max_concurrent_tasks: int = 1
    enabled: bool = True

    def __post_init__(self) -> None:
        if not self.worker_id.strip():
            raise ValueError("worker_id is required")
        if not self.role.strip():
            raise ValueError("role is required")
        if not self.capabilities:
            raise ValueError("at least one capability is required")
        if self.max_concurrent_tasks < 1:
            raise ValueError("max_concurrent_tasks must be positive")


@dataclass(frozen=True)
class WorkTask:
    title: str
    description: str
    required_capabilities: frozenset[str]
    budget_limit: Decimal
    currency: str
    acceptance_criteria: tuple[str, ...]
    dependencies: tuple[UUID, ...] = ()
    task_id: UUID = field(default_factory=uuid4)
    status: TaskStatus = TaskStatus.PLANNED
    assigned_worker_id: str | None = None
    actual_cost: Decimal = Decimal("0")
    artifact_refs: tuple[str, ...] = ()
    result_summary: str = ""
    reviewer_id: str | None = None

    def __post_init__(self) -> None:
        if not self.title.strip() or not self.description.strip():
            raise ValueError("task title and description are required")
        if not self.required_capabilities:
            raise ValueError("at least one required capability is required")
        if self.budget_limit < 0:
            raise ValueError("budget_limit cannot be negative")
        if not self.currency.strip():
            raise ValueError("currency is required")
        if not self.acceptance_criteria or any(
            not item.strip() for item in self.acceptance_criteria
        ):
            raise ValueError("non-empty acceptance criteria are required")
        if self.task_id in self.dependencies:
            raise ValueError("task cannot depend on itself")


@dataclass(frozen=True)
class TaskReview:
    task_id: UUID
    reviewer_id: str
    accepted: bool
    findings: tuple[str, ...]
    reviewed_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class WorkforceEngine:
    """In-memory task coordinator with deterministic assignment and review gates.

    Persistence, agent execution, sandboxing, policy authorization and audit
    storage are intentionally supplied by separate adapters.
    """

    def __init__(self, workers: tuple[WorkerProfile, ...] = ()) -> None:
        self._workers: dict[str, WorkerProfile] = {}
        self._tasks: dict[UUID, WorkTask] = {}
        self._reviews: list[TaskReview] = []
        for worker in workers:
            self.register_worker(worker)

    @property
    def workers(self) -> tuple[WorkerProfile, ...]:
        return tuple(self._workers.values())

    def to_snapshot(self) -> dict[str, object]:
        """Return a JSON-compatible representation of the complete workforce state."""
        return {
            "schema_version": 1,
            "workers": [
                {
                    "worker_id": worker.worker_id,
                    "role": worker.role,
                    "capabilities": sorted(worker.capabilities),
                    "max_concurrent_tasks": worker.max_concurrent_tasks,
                    "enabled": worker.enabled,
                }
                for worker in self._workers.values()
            ],
            "tasks": [
                {
                    "task_id": str(task.task_id),
                    "title": task.title,
                    "description": task.description,
                    "required_capabilities": sorted(task.required_capabilities),
                    "budget_limit": str(task.budget_limit),
                    "currency": task.currency,
                    "acceptance_criteria": list(task.acceptance_criteria),
                    "dependencies": [str(item) for item in task.dependencies],
                    "status": task.status.value,
                    "assigned_worker_id": task.assigned_worker_id,
                    "actual_cost": str(task.actual_cost),
                    "artifact_refs": list(task.artifact_refs),
                    "result_summary": task.result_summary,
                    "reviewer_id": task.reviewer_id,
                }
                for task in self._tasks.values()
            ],
            "reviews": [
                {
                    "task_id": str(review.task_id),
                    "reviewer_id": review.reviewer_id,
                    "accepted": review.accepted,
                    "findings": list(review.findings),
                    "reviewed_at": review.reviewed_at.isoformat(),
                }
                for review in self._reviews
            ],
        }

    @classmethod
    def from_snapshot(cls, snapshot: dict[str, object]) -> WorkforceEngine:
        """Restore a workforce state after validating its schema and references."""
        if snapshot.get("schema_version") != 1:
            raise WorkforceError("unsupported workforce snapshot schema")
        workers_data = snapshot.get("workers")
        tasks_data = snapshot.get("tasks")
        reviews_data = snapshot.get("reviews")
        if not isinstance(workers_data, list) or not isinstance(tasks_data, list):
            raise WorkforceError("invalid workforce snapshot collections")
        if not isinstance(reviews_data, list):
            raise WorkforceError("invalid workforce review collection")

        workers = tuple(
            WorkerProfile(
                worker_id=item["worker_id"],
                role=item["role"],
                capabilities=frozenset(item["capabilities"]),
                max_concurrent_tasks=item["max_concurrent_tasks"],
                enabled=item["enabled"],
            )
            for item in workers_data
        )
        engine = cls(workers)
        for item in tasks_data:
            task = WorkTask(
                task_id=UUID(item["task_id"]),
                title=item["title"],
                description=item["description"],
                required_capabilities=frozenset(item["required_capabilities"]),
                budget_limit=Decimal(item["budget_limit"]),
                currency=item["currency"],
                acceptance_criteria=tuple(item["acceptance_criteria"]),
                dependencies=tuple(UUID(value) for value in item["dependencies"]),
                status=TaskStatus(item["status"]),
                assigned_worker_id=item["assigned_worker_id"],
                actual_cost=Decimal(item["actual_cost"]),
                artifact_refs=tuple(item["artifact_refs"]),
                result_summary=item["result_summary"],
                reviewer_id=item["reviewer_id"],
            )
            engine.add_task(task)
            if task.status is not TaskStatus.PLANNED:
                if task.assigned_worker_id not in engine._workers:
                    raise WorkforceError("snapshot task references an unknown worker")
                if (
                    task.status
                    in (
                        TaskStatus.IN_PROGRESS,
                        TaskStatus.READY_FOR_REVIEW,
                        TaskStatus.ACCEPTED,
                        TaskStatus.REWORK_REQUIRED,
                    )
                    and task.assigned_worker_id is None
                ):
                    raise WorkforceError("active snapshot task has no assigned worker")
        for item in reviews_data:
            review = TaskReview(
                task_id=UUID(item["task_id"]),
                reviewer_id=item["reviewer_id"],
                accepted=item["accepted"],
                findings=tuple(item["findings"]),
                reviewed_at=datetime.fromisoformat(item["reviewed_at"]),
            )
            if review.task_id not in engine._tasks:
                raise WorkforceError("snapshot review references an unknown task")
            if review.reviewer_id not in engine._workers:
                raise WorkforceError("snapshot review references an unknown reviewer")
            engine._reviews.append(review)
        return engine

    @property
    def tasks(self) -> tuple[WorkTask, ...]:
        return tuple(self._tasks.values())

    @property
    def reviews(self) -> tuple[TaskReview, ...]:
        return tuple(self._reviews)

    def register_worker(self, worker: WorkerProfile) -> None:
        if worker.worker_id in self._workers:
            raise WorkforceError("worker already registered")
        self._workers[worker.worker_id] = worker

    def add_task(self, task: WorkTask) -> None:
        if task.task_id in self._tasks:
            raise WorkforceError("task already exists")
        if any(dependency not in self._tasks for dependency in task.dependencies):
            raise WorkforceError("all task dependencies must exist before task creation")
        self._tasks[task.task_id] = task

    def assign(self, task_id: UUID) -> WorkTask:
        task = self._get_task(task_id)
        if task.status not in (TaskStatus.PLANNED, TaskStatus.REWORK_REQUIRED):
            raise WorkforceError("task is not available for assignment")
        if not self._dependencies_accepted(task):
            raise WorkforceError("task dependencies are not accepted")

        candidates = [
            worker
            for worker in self._workers.values()
            if worker.enabled
            and task.required_capabilities.issubset(worker.capabilities)
            and self._active_count(worker.worker_id) < worker.max_concurrent_tasks
        ]
        if not candidates:
            raise WorkforceError("no eligible worker is currently available")

        selected = min(
            candidates,
            key=lambda worker: (self._active_count(worker.worker_id), worker.worker_id),
        )
        updated = self._replace(
            task,
            status=TaskStatus.ASSIGNED,
            assigned_worker_id=selected.worker_id,
            reviewer_id=None,
        )
        self._tasks[task_id] = updated
        return updated

    def start(self, task_id: UUID, worker_id: str) -> WorkTask:
        task = self._get_task(task_id)
        if task.status is not TaskStatus.ASSIGNED or task.assigned_worker_id != worker_id:
            raise WorkforceError("only the assigned worker can start this task")
        updated = self._replace(task, status=TaskStatus.IN_PROGRESS)
        self._tasks[task_id] = updated
        return updated

    def submit(
        self,
        task_id: UUID,
        worker_id: str,
        *,
        summary: str,
        artifact_refs: tuple[str, ...],
        actual_cost: Decimal,
    ) -> WorkTask:
        task = self._get_task(task_id)
        if task.status is not TaskStatus.IN_PROGRESS or task.assigned_worker_id != worker_id:
            raise WorkforceError("only the assigned worker can submit an in-progress task")
        if not summary.strip():
            raise ValueError("result summary is required")
        if not artifact_refs or any(not ref.strip() for ref in artifact_refs):
            raise ValueError("at least one verifiable artifact reference is required")
        if actual_cost < 0:
            raise ValueError("actual_cost cannot be negative")
        if actual_cost > task.budget_limit:
            raise WorkforceError("task budget exceeded; result requires owner review")
        updated = self._replace(
            task,
            status=TaskStatus.READY_FOR_REVIEW,
            actual_cost=actual_cost,
            artifact_refs=artifact_refs,
            result_summary=summary,
        )
        self._tasks[task_id] = updated
        return updated

    def review(
        self,
        task_id: UUID,
        reviewer_id: str,
        *,
        accepted: bool,
        findings: tuple[str, ...] = (),
        now: datetime | None = None,
    ) -> WorkTask:
        task = self._get_task(task_id)
        if task.status is not TaskStatus.READY_FOR_REVIEW:
            raise WorkforceError("task is not ready for review")
        reviewer = self._workers.get(reviewer_id)
        if (
            reviewer is None
            or not reviewer.enabled
            or "quality.review" not in reviewer.capabilities
        ):
            raise WorkforceError("reviewer lacks the quality.review capability")
        if reviewer_id == task.assigned_worker_id:
            raise WorkforceError("worker cannot review its own work")

        reviewed_at = now or datetime.now(timezone.utc)
        if reviewed_at.tzinfo is None:
            raise ValueError("review timestamp must be timezone-aware")
        review = TaskReview(task_id, reviewer_id, accepted, findings, reviewed_at)
        self._reviews.append(review)
        updated = self._replace(
            task,
            status=TaskStatus.ACCEPTED if accepted else TaskStatus.REWORK_REQUIRED,
            reviewer_id=reviewer_id,
        )
        self._tasks[task_id] = updated
        return updated

    def _get_task(self, task_id: UUID) -> WorkTask:
        try:
            return self._tasks[task_id]
        except KeyError as exc:
            raise WorkforceError("unknown task") from exc

    def _dependencies_accepted(self, task: WorkTask) -> bool:
        return all(self._tasks[item].status is TaskStatus.ACCEPTED for item in task.dependencies)

    def _active_count(self, worker_id: str) -> int:
        return sum(
            1
            for task in self._tasks.values()
            if task.assigned_worker_id == worker_id
            and task.status
            in (TaskStatus.ASSIGNED, TaskStatus.IN_PROGRESS, TaskStatus.READY_FOR_REVIEW)
        )

    @staticmethod
    def _replace(task: WorkTask, **changes: object) -> WorkTask:
        return replace(task, **changes)
