from decimal import Decimal

import pytest

from ownera.persistent_workforce import PersistentWorkforce
from ownera.worker_performance import (
    CurrencyCost,
    WorkerPerformanceError,
    WorkerPerformanceService,
)
from ownera.workforce import TaskStatus, WorkerProfile, WorkTask


def _task(title="Work item"):
    return WorkTask(
        title=title,
        description="Deliver a verifiable result.",
        required_capabilities=frozenset({"python"}),
        budget_limit=Decimal("100"),
        currency="EUR",
        acceptance_criteria=("Result meets requirements",),
    )


def _setup(tmp_path):
    database = tmp_path / "workforce.sqlite3"
    workforce = PersistentWorkforce(database)
    workforce.register_worker(
        WorkerProfile("builder-a", "backend", frozenset({"python"}))
    )
    workforce.register_worker(
        WorkerProfile("builder-b", "backend", frozenset({"python"}))
    )
    workforce.register_worker(
        WorkerProfile("reviewer", "qa", frozenset({"quality.review"}))
    )
    return workforce, database


def _complete_attempt(workforce, task, worker_id, *, accepted, cost="10"):
    assigned = workforce.assign(task.task_id)
    assert assigned.assigned_worker_id == worker_id
    workforce.start(task.task_id, worker_id)
    workforce.submit(
        task.task_id,
        worker_id,
        summary="Submitted result",
        artifact_refs=("sha256:" + "a" * 64,),
        actual_cost=Decimal(cost),
    )
    workforce.review(task.task_id, "reviewer", accepted=accepted)


def test_report_uses_reviewed_attempts_and_costs_from_event_history(tmp_path):
    workforce, database = _setup(tmp_path)
    first = _task("First")
    workforce.add_task(first)
    _complete_attempt(workforce, first, "builder-a", accepted=False, cost="12")
    reassigned = workforce.assign(first.task_id)
    assert reassigned.status is TaskStatus.ASSIGNED
    workforce.start(first.task_id, "builder-b")
    workforce.submit(
        first.task_id, "builder-b", summary="Fixed result",
        artifact_refs=("sha256:" + "b" * 64,), actual_cost=Decimal("8"),
    )
    workforce.review(first.task_id, "reviewer", accepted=True)

    report = WorkerPerformanceService(PersistentWorkforce(database)).build_report()
    by_id = {item.worker_id: item for item in report.workers}

    assert report.event_chain_verified is True
    assert report.event_count == report.event_version
    assert by_id["builder-a"].submitted_attempts == 1
    assert by_id["builder-a"].rework_attempts == 1
    assert by_id["builder-a"].acceptance_rate == 0.0
    assert by_id["builder-a"].costs_by_currency[0].total == Decimal("12")
    assert by_id["builder-b"].submitted_attempts == 1
    assert by_id["builder-b"].accepted_attempts == 1
    assert by_id["builder-b"].acceptance_rate == 1.0
    assert by_id["builder-b"].costs_by_currency[0].total == Decimal("8")


def test_pending_review_attempt_is_not_counted_as_accepted_or_rework(tmp_path):
    workforce, _ = _setup(tmp_path)
    task = _task()
    workforce.add_task(task)
    assigned = workforce.assign(task.task_id)
    workforce.start(task.task_id, assigned.assigned_worker_id)
    workforce.submit(
        task.task_id, assigned.assigned_worker_id, summary="Awaiting review",
        artifact_refs=("sha256:" + "c" * 64,), actual_cost=Decimal("4"),
    )

    report = WorkerPerformanceService(workforce).build_report()
    builder = next(item for item in report.workers if item.worker_id == "builder-a")

    assert builder.submitted_attempts == 1
    assert builder.reviewed_attempts == 0
    assert builder.pending_review_attempts == 1
    assert builder.acceptance_rate is None
    assert builder.trust_band == "UNRATED"


def test_metrics_are_separated_by_currency(tmp_path):
    workforce, _ = _setup(tmp_path)
    task = _task()
    workforce.add_task(task)
    _complete_attempt(workforce, task, "builder-a", accepted=True, cost="9")

    report = WorkerPerformanceService(workforce).build_report()
    builder = next(item for item in report.workers if item.worker_id == "builder-a")

    assert builder.costs_by_currency == (CurrencyCost("EUR", Decimal("9")),)


def test_unreviewed_attempt_is_not_falsely_marked_successful(tmp_path):
    workforce, _ = _setup(tmp_path)
    task = _task()
    workforce.add_task(task)
    assigned = workforce.assign(task.task_id)
    workforce.start(task.task_id, assigned.assigned_worker_id)
    workforce.submit(
        task.task_id, assigned.assigned_worker_id, summary="Pending",
        artifact_refs=("sha256:" + "d" * 64,), actual_cost=Decimal("5"),
    )

    report = WorkerPerformanceService(workforce).build_report()
    builder = next(item for item in report.workers if item.worker_id == "builder-a")
    assert builder.accepted_attempts == 0
    assert builder.rework_attempts == 0
    assert builder.pending_review_attempts == 1


def test_report_rejects_invalid_review_without_submission(monkeypatch, tmp_path):
    workforce, _ = _setup(tmp_path)
    task = _task()
    workforce.add_task(task)
    events = workforce.repository.event_store
    original_load = events.load

    def broken_load(aggregate_type, aggregate_id):
        history = list(original_load(aggregate_type, aggregate_id))
        history.append(type(history[-1])(
            event_id=history[-1].event_id,
            aggregate_type="workforce",
            aggregate_id="primary",
            version=history[-1].version + 1,
            event_type="TaskReviewAccepted",
            payload={"task_id": str(task.task_id), "accepted": True},
            occurred_at=history[-1].occurred_at,
            idempotency_key=None,
            previous_hash=history[-1].event_hash,
            event_hash="0" * 64,
        ))
        return tuple(history)

    monkeypatch.setattr(events, "verify", lambda *_args: True)
    monkeypatch.setattr(events, "load", broken_load)
    with pytest.raises(WorkerPerformanceError, match="no preceding submission"):
        WorkerPerformanceService(workforce).build_report()
