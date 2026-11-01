from decimal import Decimal
from uuid import NAMESPACE_URL, uuid5

import pytest

from ownera.near_market_dispatch import AssignmentExecutionSpec, dispatch_started_assignment
from ownera.persistent_workforce import PersistentWorkforce
from ownera.worker_runtime import WorkerExecutionRequest, WorkerExecutionResult
from ownera.workforce import TaskStatus, WorkerProfile


class FakeRuntime:
    def __init__(self):
        self.calls = 0

    def execute(self, request):
        self.calls += 1
        return WorkerExecutionResult(
            task_id=request.task_id, status="SUCCEEDED", exit_code=0,
            stdout="ok", stderr="", artifacts={"out/result.txt": b"verified output"},
            duration_seconds=0.01,
        )


def make_spec(status="in_progress"):
    assignment_id = "assignment-demo-001"
    task_id = str(uuid5(NAMESPACE_URL, f"ownera-near-assignment:{assignment_id}"))
    return AssignmentExecutionSpec(
        assignment_id=assignment_id, job_id="job-demo-001", status=status,
        title="Generate a verified report", description="Run the trusted local report profile.",
        budget=Decimal("10"), currency="USD", required_capabilities=frozenset({"python"}),
        acceptance_criteria=("Report artifact exists",),
        request=WorkerExecutionRequest(task_id, ("python", "-c", "pass"), artifact_paths=("out/result.txt",)),
        summary="Report generated and artifact hash registered.", actual_cost=Decimal("0.25"),
    )


def test_started_assignment_runs_and_submits_local_artifact(tmp_path):
    runtime = FakeRuntime()
    worker = WorkerProfile("near-market-worker", "backend", frozenset({"python"}))
    result = dispatch_started_assignment(make_spec(), database_path=tmp_path / "ownera.sqlite3", worker=worker, runtime=runtime)
    assert runtime.calls == 1
    assert result.artifact_refs[0].startswith("sha256:")
    state = PersistentWorkforce(tmp_path / "ownera.sqlite3")
    assert state.tasks[0].status is TaskStatus.READY_FOR_REVIEW


def test_assignment_must_be_started_before_execution(tmp_path):
    with pytest.raises(ValueError, match="already be started"):
        make_spec(status="assigned")


def test_completed_assignment_is_not_executed_twice(tmp_path):
    runtime = FakeRuntime()
    worker = WorkerProfile("near-market-worker", "backend", frozenset({"python"}))
    db = tmp_path / "ownera.sqlite3"
    dispatch_started_assignment(make_spec(), database_path=db, worker=worker, runtime=runtime)
    with pytest.raises(RuntimeError, match="already processed locally"):
        dispatch_started_assignment(make_spec(), database_path=db, worker=worker, runtime=runtime)
    assert runtime.calls == 1
