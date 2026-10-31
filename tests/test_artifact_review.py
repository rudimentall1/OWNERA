import sqlite3
from decimal import Decimal

import pytest

from ownera.artifact_registry import SQLiteArtifactRegistry
from ownera.artifact_review import ArtifactReviewError, ArtifactReviewService
from ownera.persistent_workforce import PersistentWorkforce
from ownera.workforce import WorkerProfile, WorkTask


def _submitted_task(tmp_path):
    database = tmp_path / "workforce.sqlite3"
    workforce = PersistentWorkforce(database)
    workforce.register_worker(
        WorkerProfile("builder", "backend", frozenset({"python"}))
    )
    workforce.register_worker(
        WorkerProfile("reviewer", "qa", frozenset({"quality.review"}))
    )
    task = WorkTask(
        title="Prepare evidence",
        description="Produce a verifiable artifact.",
        required_capabilities=frozenset({"python"}),
        budget_limit=Decimal("50"),
        currency="EUR",
        acceptance_criteria=("Artifact is complete",),
    )
    workforce.add_task(task)
    workforce.assign(task.task_id)
    workforce.start(task.task_id, "builder")
    registry = SQLiteArtifactRegistry(tmp_path / "artifacts.sqlite3")
    record = registry.put(
        task_id=str(task.task_id), worker_id="builder",
        artifact_name="result.txt", content=b"independent review bytes",
    )
    workforce.submit(
        task.task_id, "builder", summary="Artifact produced",
        artifact_refs=(f"sha256:{record.sha256}",), actual_cost=Decimal("5"),
    )
    return workforce, task, registry, record


def test_reviewer_receives_original_bytes_after_digest_verification(tmp_path):
    workforce, task, registry, record = _submitted_task(tmp_path)
    service = ArtifactReviewService(registry=registry, workforce=workforce)

    packet = service.load_for_review(task.task_id, "reviewer")

    assert packet.task_id == task.task_id
    assert packet.worker_id == "builder"
    assert packet.reviewer_id == "reviewer"
    assert len(packet.artifacts) == 1
    assert packet.artifacts[0].record == record
    assert packet.artifacts[0].content == b"independent review bytes"
    # Loading evidence does not accept or otherwise transition the task.
    assert workforce.tasks[0].status.value == "READY_FOR_REVIEW"


def test_worker_cannot_review_own_artifacts(tmp_path):
    workforce, task, registry, _ = _submitted_task(tmp_path)
    service = ArtifactReviewService(registry=registry, workforce=workforce)

    with pytest.raises(ArtifactReviewError, match="cannot review its own"):
        service.load_for_review(task.task_id, "builder")


def test_reviewer_requires_quality_review_capability(tmp_path):
    workforce, task, registry, _ = _submitted_task(tmp_path)
    workforce.register_worker(
        WorkerProfile("observer", "observer", frozenset({"python"}))
    )
    service = ArtifactReviewService(registry=registry, workforce=workforce)

    with pytest.raises(ArtifactReviewError, match="lacks the quality.review"):
        service.load_for_review(task.task_id, "observer")


def test_tampered_artifact_is_rejected_for_review(tmp_path):
    workforce, task, registry, record = _submitted_task(tmp_path)
    connection = sqlite3.connect(registry.database_path)
    connection.execute(
        "UPDATE worker_artifact_blobs SET content = ? WHERE sha256 = ?",
        (sqlite3.Binary(b"tampered"), record.sha256),
    )
    connection.commit()
    connection.close()
    service = ArtifactReviewService(registry=registry, workforce=workforce)

    with pytest.raises(ArtifactReviewError, match="integrity verification failed"):
        service.load_for_review(task.task_id, "reviewer")


def test_missing_task_provenance_is_rejected(tmp_path):
    workforce, task, registry, _ = _submitted_task(tmp_path)
    connection = sqlite3.connect(registry.database_path)
    connection.execute(
        "DELETE FROM worker_artifact_records WHERE task_id = ?",
        (str(task.task_id),),
    )
    connection.commit()
    connection.close()
    service = ArtifactReviewService(registry=registry, workforce=workforce)

    with pytest.raises(ArtifactReviewError, match="provenance is missing"):
        service.load_for_review(task.task_id, "reviewer")
