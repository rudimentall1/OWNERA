"""Evidence-complete quality gate for independently reviewed worker outputs."""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID

from ownera.artifact_review import ArtifactReviewService
from ownera.persistent_workforce import PersistentWorkforce
from ownera.workforce import TaskReview, TaskStatus


class QualityGateError(RuntimeError):
    """A review report is incomplete or does not match verified task evidence."""


@dataclass(frozen=True)
class CriterionAssessment:
    criterion: str
    passed: bool
    evidence_digests: tuple[str, ...]
    notes: str = ""


@dataclass(frozen=True)
class QualityGateReport:
    task_id: UUID
    reviewer_id: str
    worker_id: str
    assessments: tuple[CriterionAssessment, ...]
    overall_notes: str
    reviewed_at: datetime


@dataclass(frozen=True)
class QualityGateResult:
    accepted: bool
    report: QualityGateReport
    task_status: TaskStatus
    workforce_version: int


class QualityGateService:
    """Validate a complete criterion-by-criterion report before Workforce review.

    The reviewer supplies judgments; this service validates report completeness,
    evidence references, and separation of duties. It does not infer correctness
    from hashes or automatically inspect artifact semantics.
    """

    REPORT_PREFIX = "quality_gate_report:v1:"

    def __init__(self, workforce: PersistentWorkforce, artifact_review: ArtifactReviewService) -> None:
        self.workforce = workforce
        self.artifact_review = artifact_review

    def review(
        self,
        task_id: UUID,
        reviewer_id: str,
        assessments: tuple[CriterionAssessment, ...],
        *,
        overall_notes: str,
        now: datetime | None = None,
    ) -> QualityGateResult:
        if not overall_notes.strip():
            raise QualityGateError("overall review notes are required")

        packet = self.artifact_review.load_for_review(task_id, reviewer_id)
        task = next(
            (item for item in self.workforce.tasks if item.task_id == task_id),
            None,
        )
        if task is None:
            raise QualityGateError("review references an unknown task")
        if task.status is not TaskStatus.READY_FOR_REVIEW:
            raise QualityGateError("task is no longer ready for review")
        if task.assigned_worker_id != packet.worker_id:
            raise QualityGateError("review packet worker does not match task assignment")
        if task.reviewer_id is not None:
            raise QualityGateError("task already has a reviewer decision")
        if packet.reviewer_id == packet.worker_id:
            raise QualityGateError("worker cannot review its own work")

        packet_digests = {item.record.sha256 for item in packet.artifacts}
        expected = task.acceptance_criteria
        supplied = [item.criterion for item in assessments]
        if len(supplied) != len(set(supplied)):
            raise QualityGateError("each acceptance criterion must appear exactly once")
        if set(supplied) != set(expected) or len(supplied) != len(expected):
            raise QualityGateError("review report must cover every acceptance criterion exactly")

        for item in assessments:
            if not isinstance(item.passed, bool):
                raise QualityGateError("criterion result must be a boolean")
            if not item.evidence_digests:
                raise QualityGateError(
                    f"criterion requires at least one evidence digest: {item.criterion}"
                )
            if len(item.evidence_digests) != len(set(item.evidence_digests)):
                raise QualityGateError(
                    f"criterion contains duplicate evidence digests: {item.criterion}"
                )
            unknown = set(item.evidence_digests) - packet_digests
            if unknown:
                raise QualityGateError(
                    f"criterion references evidence outside the verified packet: {item.criterion}"
                )
            if not item.passed and not item.notes.strip():
                raise QualityGateError(
                    f"failed criterion requires actionable notes: {item.criterion}"
                )

        reviewed_at = now or datetime.now(timezone.utc)
        if reviewed_at.tzinfo is None:
            raise QualityGateError("review timestamp must be timezone-aware")

        report = QualityGateReport(
            task_id=packet.task_id,
            reviewer_id=packet.reviewer_id,
            worker_id=packet.worker_id,
            assessments=assessments,
            overall_notes=overall_notes.strip(),
            reviewed_at=reviewed_at,
        )
        accepted = all(item.passed for item in assessments)
        serialized = {
            "schema_version": 1,
            "task_id": str(report.task_id),
            "reviewer_id": report.reviewer_id,
            "worker_id": report.worker_id,
            "reviewed_at": report.reviewed_at.isoformat(),
            "overall_notes": report.overall_notes,
            "criteria": [
                {
                    "criterion": item.criterion,
                    "passed": item.passed,
                    "evidence_digests": list(item.evidence_digests),
                    "notes": item.notes,
                }
                for item in report.assessments
            ],
        }
        canonical_report = json.dumps(
            serialized, sort_keys=True, separators=(",", ":"),
            ensure_ascii=False, allow_nan=False,
        )
        findings = (
            self.REPORT_PREFIX + canonical_report,
            *(
                f"{'PASS' if item.passed else 'FAIL'}: {item.criterion}: {item.notes}".rstrip()
                for item in assessments
            ),
            f"OVERALL: {report.overall_notes}",
        )
        updated = self.workforce.review(
            task_id,
            reviewer_id,
            accepted=accepted,
            findings=findings,
            now=reviewed_at,
        )
        return QualityGateResult(
            accepted=accepted,
            report=report,
            task_status=updated.status,
            workforce_version=self.workforce.version,
        )

    @classmethod
    def extract_report(cls, review: TaskReview) -> dict[str, object]:
        """Decode the versioned structured report embedded in persisted findings."""
        matches = [
            finding[len(cls.REPORT_PREFIX):]
            for finding in review.findings
            if finding.startswith(cls.REPORT_PREFIX)
        ]
        if len(matches) != 1:
            raise QualityGateError("persisted review does not contain exactly one quality report")
        try:
            payload = json.loads(matches[0])
        except json.JSONDecodeError as exc:
            raise QualityGateError("persisted quality report is malformed") from exc
        if payload.get("schema_version") != 1:
            raise QualityGateError("unsupported quality report schema")
        return payload
