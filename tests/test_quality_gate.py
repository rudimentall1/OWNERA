from decimal import Decimal

import pytest

from ownera.artifact_registry import SQLiteArtifactRegistry
from ownera.artifact_review import ArtifactReviewService
from ownera.persistent_workforce import PersistentWorkforce
from ownera.quality_gate import (
    CriterionAssessment,
    QualityGateError,
    QualityGateService,
)
from ownera.workforce import TaskStatus, WorkerProfile, WorkTask


def _review_packet(tmp_path):
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
        acceptance_criteria=("Output is valid", "Output is documented"),
    )
    workforce.add_task(task)
    workforce.assign(task.task_id)
    workforce.start(task.task_id, "builder")
    registry = SQLiteArtifactRegistry(tmp_path / "artifacts.sqlite3")
    record = registry.put(
        task_id=str(task.task_id), worker_id="builder",
        artifact_name="result.txt", content=b"verified output",
    )
    workforce.submit(
        task.task_id, "builder", summary="Output generated",
        artifact_refs=(f"sha256:{record.sha256}",), actual_cost=Decimal("5"),
    )
    service = QualityGateService(
        workforce,
        ArtifactReviewService(registry=registry, workforce=workforce),
    )
    return workforce, task, service, record


def _assessments(digest):
    return (
        CriterionAssessment(
            "Output is valid", True, (digest,), "Validated output format."
        ),
        CriterionAssessment(
            "Output is documented", True, (digest,), "Documentation is present."
        ),
    )


def test_complete_report_accepts_task_and_persists_structured_evidence(tmp_path):
    workforce, task, service, record = _review_packet(tmp_path)

    result = service.review(
        task.task_id, "reviewer", _assessments(record.sha256), overall_notes="All criteria verified."
    )

    assert result.accepted is True
    assert result.task_status is TaskStatus.ACCEPTED
    assert workforce.tasks[0].status is TaskStatus.ACCEPTED
    persisted = PersistentWorkforce(tmp_path / "workforce.sqlite3")
    assert persisted.tasks[0].status is TaskStatus.ACCEPTED
    payload = QualityGateService.extract_report(persisted.reviews[0])
    assert payload["task_id"] == str(task.task_id)
    assert len(payload["criteria"]) == 2
    assert payload["criteria"][0]["evidence_digests"] == [record.sha256]


def test_failed_criterion_returns_task_for_rework_with_actionable_notes(tmp_path):
    workforce, task, service, record = _review_packet(tmp_path)
    assessments = (
        CriterionAssessment("Output is valid", True, (record.sha256,)),
        CriterionAssessment(
            "Output is documented", False, (record.sha256,),
            "Add missing installation and usage instructions.",
        ),
    )

    result = service.review(
        task.task_id, "reviewer", assessments, overall_notes="One criterion failed."
    )

    assert result.accepted is False
    assert result.task_status is TaskStatus.REWORK_REQUIRED
    assert workforce.tasks[0].status is TaskStatus.REWORK_REQUIRED
    payload = QualityGateService.extract_report(workforce.reviews[0])
    assert payload["criteria"][1]["passed"] is False


def test_incomplete_report_cannot_transition_task(tmp_path):
    workforce, task, service, record = _review_packet(tmp_path)

    with pytest.raises(QualityGateError, match="cover every acceptance criterion"):
        service.review(
            task.task_id, "reviewer",
            (CriterionAssessment("Output is valid", True, (record.sha256,)),),
            overall_notes="Incomplete.",
        )

    assert workforce.tasks[0].status is TaskStatus.READY_FOR_REVIEW
    assert workforce.reviews == ()


def test_duplicate_criterion_is_rejected(tmp_path):
    workforce, task, service, record = _review_packet(tmp_path)
    duplicate = (
        CriterionAssessment("Output is valid", True, (record.sha256,)),
        CriterionAssessment("Output is valid", True, (record.sha256,)),
    )

    with pytest.raises(QualityGateError, match="exactly once"):
        service.review(
            task.task_id, "reviewer", duplicate, overall_notes="Duplicate."
        )


def test_unverified_evidence_reference_is_rejected(tmp_path):
    workforce, task, service, record = _review_packet(tmp_path)
    invalid = (
        CriterionAssessment("Output is valid", True, ("0" * 64,)),
        CriterionAssessment("Output is documented", True, (record.sha256,)),
    )

    with pytest.raises(QualityGateError, match="outside the verified packet"):
        service.review(
            task.task_id, "reviewer", invalid, overall_notes="Bad evidence reference."
        )


def test_failed_criterion_requires_actionable_notes(tmp_path):
    workforce, task, service, record = _review_packet(tmp_path)
    invalid = (
        CriterionAssessment("Output is valid", True, (record.sha256,)),
        CriterionAssessment("Output is documented", False, (record.sha256,)),
    )

    with pytest.raises(QualityGateError, match="actionable notes"):
        service.review(
            task.task_id, "reviewer", invalid, overall_notes="Needs work."
        )


def test_report_requires_notes_and_rejects_naive_timestamp(tmp_path):
    workforce, task, service, record = _review_packet(tmp_path)
    with pytest.raises(QualityGateError, match="overall review notes"):
        service.review(
            task.task_id, "reviewer", _assessments(record.sha256), overall_notes=" "
        )

    from datetime import datetime
    with pytest.raises(QualityGateError, match="timezone-aware"):
        service.review(
            task.task_id, "reviewer", _assessments(record.sha256), overall_notes="reviewed",
            now=datetime(2026, 10, 31, 12, 0, 0),
        )
