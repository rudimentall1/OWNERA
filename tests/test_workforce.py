from decimal import Decimal

import pytest

from ownera.workforce import (
    TaskStatus,
    WorkerProfile,
    WorkforceEngine,
    WorkforceError,
    WorkTask,
)


def _task(*, dependencies=()):
    return WorkTask(
        title="Implement API endpoint",
        description="Build the agreed endpoint and tests.",
        required_capabilities=frozenset({"python", "fastapi"}),
        budget_limit=Decimal("20"),
        currency="EUR",
        acceptance_criteria=("Endpoint returns expected schema", "Tests pass"),
        dependencies=dependencies,
    )


def _engine():
    return WorkforceEngine(
        (
            WorkerProfile("backend-1", "backend", frozenset({"python", "fastapi"})),
            WorkerProfile("qa-1", "qa", frozenset({"quality.review"})),
        )
    )


def test_task_requires_independent_review_before_acceptance():
    engine = _engine()
    task = _task()
    engine.add_task(task)

    assigned = engine.assign(task.task_id)
    assert assigned.assigned_worker_id == "backend-1"
    assert assigned.status is TaskStatus.ASSIGNED

    engine.start(task.task_id, "backend-1")
    submitted = engine.submit(
        task.task_id,
        "backend-1",
        summary="Endpoint and tests are ready.",
        artifact_refs=("git:commit:abc123", "ci:run:42"),
        actual_cost=Decimal("12.50"),
    )
    assert submitted.status is TaskStatus.READY_FOR_REVIEW

    accepted = engine.review(task.task_id, "qa-1", accepted=True)
    assert accepted.status is TaskStatus.ACCEPTED
    assert accepted.reviewer_id == "qa-1"
    assert len(engine.reviews) == 1


def test_worker_cannot_review_own_work():
    engine = _engine()
    task = _task()
    engine.add_task(task)
    engine.assign(task.task_id)
    engine.start(task.task_id, "backend-1")
    engine.submit(
        task.task_id,
        "backend-1",
        summary="Done",
        artifact_refs=("git:commit:abc123",),
        actual_cost=Decimal("1"),
    )

    with pytest.raises(WorkforceError, match="cannot review its own work"):
        engine.review(task.task_id, "backend-1", accepted=True)


def test_task_cannot_be_assigned_until_dependencies_are_accepted():
    engine = _engine()
    first = _task()
    engine.add_task(first)
    second = _task(dependencies=(first.task_id,))
    engine.add_task(second)

    with pytest.raises(WorkforceError, match="dependencies are not accepted"):
        engine.assign(second.task_id)


def test_task_budget_is_enforced_before_review():
    engine = _engine()
    task = _task()
    engine.add_task(task)
    engine.assign(task.task_id)
    engine.start(task.task_id, "backend-1")

    with pytest.raises(WorkforceError, match="budget exceeded"):
        engine.submit(
            task.task_id,
            "backend-1",
            summary="Overspent",
            artifact_refs=("git:commit:abc123",),
            actual_cost=Decimal("20.01"),
        )


def test_missing_artifact_evidence_is_rejected():
    engine = _engine()
    task = _task()
    engine.add_task(task)
    engine.assign(task.task_id)
    engine.start(task.task_id, "backend-1")

    with pytest.raises(ValueError, match="verifiable artifact"):
        engine.submit(
            task.task_id,
            "backend-1",
            summary="Trust me, it works",
            artifact_refs=(),
            actual_cost=Decimal("1"),
        )


def test_no_worker_is_assigned_without_required_capabilities():
    engine = WorkforceEngine((WorkerProfile("frontend", "frontend", frozenset({"react"})),))
    task = _task()
    engine.add_task(task)

    with pytest.raises(WorkforceError, match="no eligible worker"):
        engine.assign(task.task_id)
