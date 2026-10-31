from decimal import Decimal
from uuid import uuid4

import pytest

from ownera.artifact_registry import SQLiteArtifactRegistry
from ownera.persistent_workforce import PersistentWorkforce
from ownera.worker_execution import WorkerExecutionFailed, WorkerExecutionService
from ownera.worker_runtime import WorkerExecutionRequest, WorkerExecutionResult
from ownera.workforce import WorkerProfile, WorkTask


class FakeRuntime:
    def __init__(self, result):
        self.result = result
        self.calls = 0

    def execute(self, request):
        self.calls += 1
        return self.result


def setup_workforce(tmp_path):
    workforce = PersistentWorkforce(tmp_path / "workforce.sqlite3")
    workforce.register_worker(
        WorkerProfile("builder", "backend", frozenset({"python"}))
    )
    task = WorkTask(
        title="Build deliverable",
        description="Produce a reviewable artifact.",
        required_capabilities=frozenset({"python"}),
        budget_limit=Decimal("100"),
        currency="EUR",
        acceptance_criteria=("Artifact exists and is reviewable",),
    )
    workforce.add_task(task)
    workforce.assign(task.task_id)
    workforce.start(task.task_id, "builder")
    return workforce, task


def test_execution_registers_artifact_then_persists_submission(tmp_path):
    workforce, task = setup_workforce(tmp_path)
    request = WorkerExecutionRequest(
        str(task.task_id), ("python", "-c", "pass"),
        artifact_paths=("reports/result.txt",),
    )
    runtime = FakeRuntime(
        WorkerExecutionResult(
            task_id=str(task.task_id), status="SUCCEEDED", exit_code=0,
            stdout="", stderr="", artifacts={"reports/result.txt": b"deliverable"},
            duration_seconds=0.1,
        )
    )
    registry = SQLiteArtifactRegistry(tmp_path / "artifacts.sqlite3")
    service = WorkerExecutionService(
        runtime=runtime, registry=registry, workforce=workforce
    )

    result = service.execute_and_submit(
        request, worker_id="builder", summary="Deliverable generated",
        actual_cost=Decimal("12"),
    )

    assert runtime.calls == 1
    assert result.artifact_refs == (f"sha256:{result.artifact_records[0].sha256}",)
    assert registry.get(result.artifact_records[0].sha256) == b"deliverable"
    refreshed = PersistentWorkforce(tmp_path / "workforce.sqlite3")
    submitted = next(item for item in refreshed.tasks if item.task_id == task.task_id)
    assert submitted.status.value == "READY_FOR_REVIEW"
    assert submitted.artifact_refs == result.artifact_refs


def test_failed_runtime_does_not_submit_task_or_register_artifacts(tmp_path):
    workforce, task = setup_workforce(tmp_path)
    request = WorkerExecutionRequest(str(task.task_id), ("python", "-V"))
    runtime = FakeRuntime(
        WorkerExecutionResult(
            task_id=str(task.task_id), status="FAILED", exit_code=9,
            stdout="", stderr="failed", artifacts={}, duration_seconds=0.1,
        )
    )
    registry = SQLiteArtifactRegistry(tmp_path / "artifacts.sqlite3")
    service = WorkerExecutionService(runtime=runtime, registry=registry, workforce=workforce)

    with pytest.raises(WorkerExecutionFailed, match="did not succeed"):
        service.execute_and_submit(
            request, worker_id="builder", summary="failed",
            actual_cost=Decimal("1"),
        )

    assert workforce.tasks[0].status.value == "IN_PROGRESS"
    assert registry.list_for_task(str(task.task_id)) == ()


def test_unassigned_worker_cannot_invoke_runtime(tmp_path):
    workforce, task = setup_workforce(tmp_path)
    request = WorkerExecutionRequest(str(task.task_id), ("python", "-V"))
    runtime = FakeRuntime(None)
    service = WorkerExecutionService(
        runtime=runtime,
        registry=SQLiteArtifactRegistry(tmp_path / "artifacts.sqlite3"),
        workforce=workforce,
    )

    with pytest.raises(WorkerExecutionFailed, match="assigned worker"):
        service.execute_and_submit(
            request, worker_id="intruder", summary="no", actual_cost=Decimal("0")
        )
    assert runtime.calls == 0


def test_runtime_cannot_submit_artifact_for_another_task(tmp_path):
    workforce, task = setup_workforce(tmp_path)
    request = WorkerExecutionRequest(str(task.task_id), ("python", "-V"))
    runtime = FakeRuntime(
        WorkerExecutionResult(
            task_id=str(uuid4()), status="SUCCEEDED", exit_code=0,
            stdout="", stderr="", artifacts={"result.txt": b"bad"},
            duration_seconds=0.1,
        )
    )
    service = WorkerExecutionService(
        runtime=runtime,
        registry=SQLiteArtifactRegistry(tmp_path / "artifacts.sqlite3"),
        workforce=workforce,
    )

    with pytest.raises(WorkerExecutionFailed, match="different task"):
        service.execute_and_submit(
            request, worker_id="builder", summary="wrong task",
            actual_cost=Decimal("1"),
        )
    assert workforce.tasks[0].status.value == "IN_PROGRESS"
