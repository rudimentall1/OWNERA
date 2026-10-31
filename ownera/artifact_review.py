"""Independent reviewer access to registered worker artifacts."""
from __future__ import annotations

import re
from dataclasses import dataclass
from uuid import UUID

from ownera.artifact_registry import ArtifactRecord, SQLiteArtifactRegistry
from ownera.persistent_workforce import PersistentWorkforce
from ownera.workforce import TaskStatus


class ArtifactReviewError(RuntimeError):
    """Reviewer cannot safely load the task's submitted artifact evidence."""


@dataclass(frozen=True)
class ReviewArtifact:
    record: ArtifactRecord
    content: bytes


@dataclass(frozen=True)
class ArtifactReviewPacket:
    task_id: UUID
    reviewer_id: str
    worker_id: str
    artifacts: tuple[ReviewArtifact, ...]


class ArtifactReviewService:
    """Load and verify submitted artifacts without deciding task acceptance."""

    _REF = re.compile(r"^sha256:([a-f0-9]{64})$")

    def __init__(
        self, *, registry: SQLiteArtifactRegistry, workforce: PersistentWorkforce
    ) -> None:
        self.registry = registry
        self.workforce = workforce

    def load_for_review(
        self, task_id: UUID, reviewer_id: str
    ) -> ArtifactReviewPacket:
        task = next(
            (item for item in self.workforce.tasks if item.task_id == task_id), None
        )
        if task is None:
            raise ArtifactReviewError(f"unknown task: {task_id}")
        if task.status is not TaskStatus.READY_FOR_REVIEW:
            raise ArtifactReviewError("task is not ready for review")
        reviewer = next(
            (item for item in self.workforce.workers if item.worker_id == reviewer_id),
            None,
        )
        if (
            reviewer is None
            or not reviewer.enabled
            or "quality.review" not in reviewer.capabilities
        ):
            raise ArtifactReviewError("reviewer lacks the quality.review capability")
        if reviewer_id == task.assigned_worker_id:
            raise ArtifactReviewError("worker cannot review its own artifacts")
        if not task.artifact_refs:
            raise ArtifactReviewError("task has no submitted artifact references")

        records = self.registry.list_for_task(str(task_id))
        by_digest = {record.sha256: record for record in records}
        artifacts: list[ReviewArtifact] = []
        for reference in task.artifact_refs:
            match = self._REF.fullmatch(reference)
            if match is None:
                raise ArtifactReviewError(
                    "task contains a reference that is not a registered SHA-256 artifact"
                )
            digest = match.group(1)
            record = by_digest.get(digest)
            if record is None:
                raise ArtifactReviewError(
                    f"artifact provenance is missing for digest: {digest}"
                )
            if record.worker_id != task.assigned_worker_id:
                raise ArtifactReviewError(
                    f"artifact worker provenance mismatch for digest: {digest}"
                )
            try:
                content = self.registry.get(digest)
            except Exception as exc:
                raise ArtifactReviewError(
                    f"artifact integrity verification failed for digest: {digest}"
                ) from exc
            if len(content) != record.size_bytes:
                raise ArtifactReviewError(
                    f"artifact size mismatch for digest: {digest}"
                )
            artifacts.append(ReviewArtifact(record=record, content=content))

        return ArtifactReviewPacket(
            task_id=task_id,
            reviewer_id=reviewer_id,
            worker_id=task.assigned_worker_id or "",
            artifacts=tuple(artifacts),
        )
