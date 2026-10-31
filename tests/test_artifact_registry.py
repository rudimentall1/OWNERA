import hashlib
import sqlite3

import pytest

from ownera.artifact_registry import (
    ArtifactIntegrityError,
    ArtifactNotFoundError,
    SQLiteArtifactRegistry,
)


def test_put_get_and_verify_artifact_after_reopen(tmp_path):
    database = tmp_path / "ownera.sqlite3"
    registry = SQLiteArtifactRegistry(database)
    content = b"independently reviewable worker output"
    record = registry.put(
        task_id="task-1",
        worker_id="builder-1",
        artifact_name="result.txt",
        content=content,
        media_type="text/plain",
    )

    reopened = SQLiteArtifactRegistry(database)
    assert reopened.get(record.sha256) == content
    assert reopened.verify(record.sha256) is True
    assert record.sha256 == hashlib.sha256(content).hexdigest()
    assert record.size_bytes == len(content)
    assert record.media_type == "text/plain"


def test_identical_content_is_deduplicated_across_tasks(tmp_path):
    database = tmp_path / "ownera.sqlite3"
    registry = SQLiteArtifactRegistry(database)
    first = registry.put(
        task_id="task-1", worker_id="worker-a",
        artifact_name="output.bin", content=b"same bytes",
    )
    second = registry.put(
        task_id="task-2", worker_id="worker-b",
        artifact_name="output.bin", content=b"same bytes",
    )

    connection = sqlite3.connect(database)
    blob_count = connection.execute(
        "SELECT COUNT(*) FROM worker_artifact_blobs"
    ).fetchone()[0]
    record_count = connection.execute(
        "SELECT COUNT(*) FROM worker_artifact_records"
    ).fetchone()[0]
    connection.close()

    assert first.sha256 == second.sha256
    assert blob_count == 1
    assert record_count == 2


def test_same_artifact_name_with_new_content_gets_new_digest(tmp_path):
    registry = SQLiteArtifactRegistry(tmp_path / "ownera.sqlite3")
    first = registry.put(
        task_id="task-1", worker_id="worker-a",
        artifact_name="report.json", content=b'{"version":1}',
    )
    second = registry.put(
        task_id="task-1", worker_id="worker-a",
        artifact_name="report.json", content=b'{"version":2}',
    )
    assert first.sha256 != second.sha256
    assert len(registry.list_for_task("task-1")) == 2


def test_tampered_blob_is_detected_on_read(tmp_path):
    database = tmp_path / "ownera.sqlite3"
    registry = SQLiteArtifactRegistry(database)
    record = registry.put(
        task_id="task-1", worker_id="worker-a",
        artifact_name="output.txt", content=b"original",
    )
    connection = sqlite3.connect(database)
    connection.execute(
        "UPDATE worker_artifact_blobs SET content = ? WHERE sha256 = ?",
        (sqlite3.Binary(b"tampered"), record.sha256),
    )
    connection.commit()
    connection.close()

    with pytest.raises(ArtifactIntegrityError, match="integrity check failed"):
        registry.get(record.sha256)


def test_missing_digest_and_malformed_digest_fail_clearly(tmp_path):
    registry = SQLiteArtifactRegistry(tmp_path / "ownera.sqlite3")
    with pytest.raises(ArtifactNotFoundError):
        registry.get("a" * 64)
    with pytest.raises(ValueError, match="64 lowercase"):
        registry.get("../not-a-digest")


def test_rejects_path_traversal_and_unsafe_identifiers(tmp_path):
    registry = SQLiteArtifactRegistry(tmp_path / "ownera.sqlite3")
    with pytest.raises(ValueError, match="plain filename"):
        registry.put(
            task_id="task-1", worker_id="worker-a",
            artifact_name="../secret.txt", content=b"x",
        )
    with pytest.raises(ValueError, match="task_id"):
        registry.put(
            task_id="../task", worker_id="worker-a",
            artifact_name="output.txt", content=b"x",
        )


def test_enforces_artifact_size_limit(tmp_path):
    registry = SQLiteArtifactRegistry(
        tmp_path / "ownera.sqlite3", max_artifact_bytes=4
    )
    with pytest.raises(ValueError, match="size limit"):
        registry.put(
            task_id="task-1", worker_id="worker-a",
            artifact_name="large.bin", content=b"12345",
        )


def test_lists_only_records_for_requested_task(tmp_path):
    registry = SQLiteArtifactRegistry(tmp_path / "ownera.sqlite3")
    expected = registry.put(
        task_id="task-1", worker_id="worker-a",
        artifact_name="one.txt", content=b"one",
    )
    registry.put(
        task_id="task-2", worker_id="worker-b",
        artifact_name="two.txt", content=b"two",
    )

    records = registry.list_for_task("task-1")
    assert len(records) == 1
    assert records[0] == expected
