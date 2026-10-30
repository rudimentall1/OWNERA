import sqlite3
from decimal import Decimal

import pytest

from ownera.workforce import (
    TaskStatus,
    WorkerProfile,
    WorkforceEngine,
    WorkTask,
)
from ownera.workforce_repository import (
    SnapshotConflict,
    SnapshotIntegrityError,
    SQLiteWorkforceRepository,
)


def _engine_with_completed_task():
    engine = WorkforceEngine(
        (
            WorkerProfile("builder", "backend", frozenset({"python"})),
            WorkerProfile("reviewer", "qa", frozenset({"quality.review"})),
        )
    )
    task = WorkTask(
        title="Build API",
        description="Implement the agreed API.",
        required_capabilities=frozenset({"python"}),
        budget_limit=Decimal("100"),
        currency="EUR",
        acceptance_criteria=("Endpoint works",),
    )
    engine.add_task(task)
    assigned = engine.assign(task.task_id)
    engine.start(task.task_id, assigned.assigned_worker_id)
    engine.submit(
        task.task_id,
        assigned.assigned_worker_id,
        summary="Implemented API",
        artifact_refs=("https://example.invalid/commit/abc",),
        actual_cost=Decimal("35.50"),
    )
    engine.review(task.task_id, "reviewer", accepted=True)
    return engine


def test_workforce_state_restores_after_process_style_reopen(tmp_path):
    database = tmp_path / "ownera.sqlite3"
    repository = SQLiteWorkforceRepository(database)
    original = _engine_with_completed_task()
    assert repository.save(original, expected_version=0) == 1

    reopened_repository = SQLiteWorkforceRepository(database)
    restored = reopened_repository.load()

    assert restored is not None
    assert restored.version == 1
    assert restored.engine.tasks == original.tasks
    assert restored.engine.reviews == original.reviews
    assert restored.engine.workers == original.workers
    assert restored.engine.tasks[0].status is TaskStatus.ACCEPTED


def test_snapshot_save_rejects_stale_writer(tmp_path):
    repository = SQLiteWorkforceRepository(tmp_path / "ownera.sqlite3")
    engine = WorkforceEngine(
        (WorkerProfile("builder", "backend", frozenset({"python"})),)
    )
    repository.save(engine, expected_version=0)

    with pytest.raises(SnapshotConflict, match="expected snapshot version 0, found 1"):
        repository.save(engine, expected_version=0)


def test_snapshot_digest_detects_database_tampering(tmp_path):
    database = tmp_path / "ownera.sqlite3"
    repository = SQLiteWorkforceRepository(database)
    repository.save(_engine_with_completed_task(), expected_version=0)

    connection = sqlite3.connect(database)
    connection.execute(
        "UPDATE workforce_snapshots SET payload_json = ?",
        ('{"schema_version":1,"workers":[],"tasks":[],"reviews":[]}',),
    )
    connection.commit()
    connection.close()

    with pytest.raises(SnapshotIntegrityError, match="digest mismatch"):
        repository.load()


def test_empty_repository_has_no_snapshot(tmp_path):
    repository = SQLiteWorkforceRepository(tmp_path / "ownera.sqlite3")
    assert repository.load() is None
