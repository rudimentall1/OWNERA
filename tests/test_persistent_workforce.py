from decimal import Decimal

import pytest

from ownera.persistent_workforce import PersistentWorkforce
from ownera.workforce import (
    TaskStatus,
    WorkerProfile,
    WorkTask,
)
from ownera.workforce_repository import SnapshotConflict


def _task():
    return WorkTask(
        title="Implement service",
        description="Implement the accepted service scope.",
        required_capabilities=frozenset({"python"}),
        budget_limit=Decimal("250"),
        currency="EUR",
        acceptance_criteria=("Service works",),
    )


def test_every_workforce_transition_is_persisted_before_success(tmp_path):
    database = tmp_path / "ownera.sqlite3"
    workforce = PersistentWorkforce(database)
    workforce.register_worker(
        WorkerProfile("builder", "backend", frozenset({"python"}))
    )
    workforce.register_worker(
        WorkerProfile("reviewer", "qa", frozenset({"quality.review"}))
    )
    task = _task()
    workforce.add_task(task)
    assigned = workforce.assign(task.task_id)
    workforce.start(task.task_id, assigned.assigned_worker_id)
    workforce.submit(
        task.task_id,
        assigned.assigned_worker_id,
        summary="Implementation complete",
        artifact_refs=("commit:abc123",),
        actual_cost=Decimal("80"),
    )
    workforce.review(task.task_id, "reviewer", accepted=True)

    restored = PersistentWorkforce(database)

    assert restored.version == workforce.version
    assert restored.tasks[0].status is TaskStatus.ACCEPTED
    assert restored.tasks[0].artifact_refs == ("commit:abc123",)
    assert len(restored.reviews) == 1


def test_stale_process_reloads_committed_state_and_rejects_write(tmp_path):
    database = tmp_path / "ownera.sqlite3"
    first = PersistentWorkforce(database)
    second = PersistentWorkforce(database)
    first.register_worker(
        WorkerProfile("builder", "backend", frozenset({"python"}))
    )

    with pytest.raises(SnapshotConflict):
        second.register_worker(
            WorkerProfile("reviewer", "qa", frozenset({"quality.review"}))
        )

    assert second.workers == first.workers
    assert second.version == first.version
