import json

import pytest

from ownera.near_market import NearMarketError
from ownera.near_market_lifecycle import NearMarketLifecycle


class FakeResponse:
    def __init__(self, payload):
        self.payload = json.dumps(payload).encode()
    def __enter__(self): return self
    def __exit__(self, *args): return False
    def read(self, *args): return self.payload


def test_start_uses_exact_path_post_no_body_and_bearer():
    seen = []
    def opener(request, timeout):
        seen.append((request, timeout))
        return FakeResponse({"startedAt": "2026-11-01T12:00:00Z"})
    started = NearMarketLifecycle("aat_test", opener=opener).start_assignment("assignment-1")
    req, _timeout = seen[0]
    assert started == "2026-11-01T12:00:00Z"
    assert req.full_url.endswith("/v1/assignments/assignment-1/start")
    assert req.get_method() == "POST" and req.data is None
    assert req.get_header("Authorization") == "Bearer aat_test"


def test_submit_sends_openapi_body_and_requires_confirmed_response():
    seen = []
    def opener(request, timeout):
        seen.append(request)
        return FakeResponse({"assignmentId": "assignment-2", "status": "submitted", "submittedAt": "2026-11-01T12:01:00Z", "deliverableHash": "abc"})
    result = NearMarketLifecycle("aat_test", opener=opener).submit_deliverable("assignment-2", "# Result\nDone", files=("https://market.near.ai/files/token/out.txt",))
    req = seen[0]
    assert req.full_url.endswith("/v1/assignments/assignment-2/submit")
    assert json.loads(req.data) == {"deliverableMarkdown": "# Result\nDone", "files": ["https://market.near.ai/files/token/out.txt"]}
    assert req.get_header("Content-type") == "application/json"
    assert result.status == "submitted" and result.deliverable_hash == "abc"


def test_submit_rejects_empty_and_oversized_before_network():
    calls = []
    api = NearMarketLifecycle("aat_test", opener=lambda *a, **k: calls.append(1))
    with pytest.raises(ValueError, match="256 KiB"):
        api.submit_deliverable("assignment-1", "")
    with pytest.raises(ValueError, match="256 KiB"):
        api.submit_deliverable("assignment-1", "x" * (256 * 1024 + 1))
    assert calls == []


def test_submit_rejects_non_confirming_response():
    api = NearMarketLifecycle("aat_test", opener=lambda *a, **k: FakeResponse({"assignmentId": "assignment-1", "status": "in_progress"}))
    with pytest.raises(NearMarketError, match="does not confirm"):
        api.submit_deliverable("assignment-1", "# Result")


def test_real_lifecycle_orchestrates_start_worker_and_submit(tmp_path):
    from decimal import Decimal
    from uuid import NAMESPACE_URL, uuid5

    from ownera.near_market_dispatch import AssignmentExecutionSpec
    from ownera.near_market_lifecycle import execute_and_deliver_assignment
    from ownera.worker_runtime import WorkerExecutionRequest, WorkerExecutionResult
    from ownera.workforce import WorkerProfile

    class Runtime:
        def execute(self, request):
            return WorkerExecutionResult(
                task_id=request.task_id, status="SUCCEEDED", exit_code=0,
                stdout="ok", stderr="", artifacts={"out/result.txt": b"buyer-visible result"},
                duration_seconds=0.01,
            )

    requests = []
    import hashlib
    artifact = b"buyer-visible result"
    responses = [
        {"startedAt": "2026-11-01T12:00:00Z"},
        {"fileId": "file-live", "directUploadUrl": "https://objects.example/live"},
        {"fileId": "file-live", "filename": "out__result.txt", "byteSize": len(artifact), "sha256": hashlib.sha256(artifact).hexdigest(), "contentType": "text/plain"},
        {"assignments": [{"assignment": {"assignmentId": "assignment-live", "status": "in_progress"}, "job": {}}]},
        {"assignmentId": "assignment-live", "status": "submitted", "submittedAt": "2026-11-01T12:01:00Z", "deliverableHash": "hash"},
    ]
    def opener(request, timeout):
        requests.append(request)
        if request.full_url == "https://objects.example/live":
            assert request.get_method() == "PUT" and request.data == artifact
            return FakeResponse({})
        return FakeResponse(responses.pop(0))

    assignment_id = "assignment-live"
    task_id = str(uuid5(NAMESPACE_URL, f"ownera-near-assignment:{assignment_id}"))
    spec = AssignmentExecutionSpec(
        assignment_id=assignment_id, job_id="job-live", status="in_progress",
        title="Generate a report", description="Trusted task profile.",
        budget=Decimal("10"), currency="USD", required_capabilities=frozenset({"python"}),
        acceptance_criteria=("Result is present",),
        request=WorkerExecutionRequest(task_id, ("python", "-c", "pass"), artifact_paths=("out/result.txt",)),
        summary="Generated and verified the report.", actual_cost=Decimal("0.10"),
    )
    item = {
        "assignment": {"assignmentId": assignment_id, "jobId": "job-live", "status": "in_progress", "startedAt": None},
        "job": {"jobId": "job-live", "title": "Generate a report", "description": "Untrusted buyer brief"},
    }
    local, remote = execute_and_deliver_assignment(
        item, spec, database_path=tmp_path / "ownera.sqlite3",
        worker=WorkerProfile("near-worker", "backend", frozenset({"python"})),
        runtime=Runtime(), lifecycle=NearMarketLifecycle("aat_test", opener=opener),
    )
    assert local.runtime_status == "SUCCEEDED"
    assert remote.status == "submitted"
    assert requests[0].full_url.endswith(f"/v1/assignments/{assignment_id}/start")
    assert requests[1].full_url.endswith("/v1/files")
    assert requests[2].full_url == "https://objects.example/live"
    assert requests[3].full_url.endswith("/v1/files/file-live/complete")
    assert requests[4].full_url.startswith("https://market.near.ai/v1/agents/me/assignments?")
    assert requests[4].get_method() == "GET"
    assert requests[5].full_url.endswith(f"/v1/assignments/{assignment_id}/submit")
    submitted = json.loads(requests[5].data)
    assert submitted["files"] == ["file-live"]
    assert "buyer-visible result" in submitted["deliverableMarkdown"]
    assert "Generated and verified" in submitted["deliverableMarkdown"]


def test_upload_file_reserve_put_complete_and_verify_sha256():
    import hashlib

    content = b"\\x00\\x01binary-data"
    calls = []
    def opener(request, timeout):
        calls.append(request)
        if request.full_url.endswith("/v1/files"):
            return FakeResponse({"fileId": "file-uuid", "directUploadUrl": "https://objects.example/upload/signed"})
        if request.full_url == "https://objects.example/upload/signed":
            assert request.get_method() == "PUT"
            assert request.data == content
            assert request.get_header("Authorization") is None
            return FakeResponse({})
        if request.full_url.endswith("/v1/files/file-uuid/complete"):
            return FakeResponse({"fileId": "file-uuid", "filename": "archive.bin", "byteSize": len(content), "sha256": hashlib.sha256(content).hexdigest(), "contentType": "application/octet-stream"})
        raise AssertionError(request.full_url)
    file_id = NearMarketLifecycle("aat_test", opener=opener).upload_file("archive.bin", content)
    assert file_id == "file-uuid"
    assert calls[0].get_method() == "POST"
    assert json.loads(calls[0].data) == {"filename": "archive.bin", "byteSize": len(content)}
    assert calls[2].full_url.endswith("/v1/files/file-uuid/complete")


def test_upload_rejects_hash_mismatch_and_unsafe_presigned_url():
    def bad_hash(request, timeout):
        if request.full_url.endswith("/v1/files"):
            return FakeResponse({"fileId": "file-uuid", "directUploadUrl": "https://objects.example/upload"})
        if request.full_url == "https://objects.example/upload":
            return FakeResponse({})
        return FakeResponse({"fileId": "file-uuid", "byteSize": 3, "sha256": "bad"})
    with pytest.raises(NearMarketError, match="does not match"):
        NearMarketLifecycle("aat_test", opener=bad_hash).upload_file("a.bin", b"abc")
    unsafe = NearMarketLifecycle("aat_test", opener=lambda request, timeout: FakeResponse({"fileId": "f", "directUploadUrl": "http://evil.example/upload"}))
    with pytest.raises(NearMarketError, match="unsafe"):
        unsafe.upload_file("a.bin", b"abc")


def test_delivery_reconciliation_detects_remote_success_without_duplicate_submit(tmp_path):
    import sqlite3

    from ownera.near_market_lifecycle import _init_delivery_outbox, retry_prepared_delivery

    db_path = tmp_path / "ownera.sqlite3"
    _init_delivery_outbox(db_path)
    with sqlite3.connect(db_path) as db:
        db.execute("INSERT INTO near_market_delivery_outbox(assignment_id,task_id,markdown,state,updated_at) VALUES('assignment-reconcile','task-1','# Delivery','READY_TO_SUBMIT','now')")
    calls = []
    def opener(request, timeout):
        calls.append(request)
        return FakeResponse({"assignments": [{"assignment": {"assignmentId": "assignment-reconcile", "status": "submitted"}, "job": {}}]})
    result = retry_prepared_delivery("assignment-reconcile", database_path=db_path, lifecycle=NearMarketLifecycle("aat_test", opener=opener))
    assert result.status == "submitted"
    assert len(calls) == 1 and calls[0].get_method() == "GET"
    with sqlite3.connect(db_path) as db:
        state = db.execute("SELECT state FROM near_market_delivery_outbox WHERE assignment_id='assignment-reconcile'").fetchone()[0]
    assert state == "SUBMITTED"


def test_delivery_reconciliation_resumes_partial_uploads_without_worker(tmp_path):
    import hashlib
    import sqlite3

    from ownera.artifact_registry import SQLiteArtifactRegistry
    from ownera.near_market_lifecycle import _init_delivery_outbox, retry_prepared_delivery

    db_path = tmp_path / "ownera.sqlite3"
    registry = SQLiteArtifactRegistry(db_path)
    content = b"recovered artifact"
    registry.put(task_id="task-2", worker_id="worker-2", artifact_name="result.txt", content=content, media_type="text/plain")
    _init_delivery_outbox(db_path)
    with sqlite3.connect(db_path) as db:
        db.execute("INSERT INTO near_market_delivery_outbox(assignment_id,task_id,markdown,state,updated_at) VALUES('assignment-partial','task-2','# Delivery','PREPARING','now')")
    responses = [
        {"fileId": "file-recovered", "directUploadUrl": "https://objects.example/recover"},
        {"fileId": "file-recovered", "filename": "result.txt", "byteSize": len(content), "sha256": hashlib.sha256(content).hexdigest(), "contentType": "text/plain"},
        {"assignments": [{"assignment": {"assignmentId": "assignment-partial", "status": "in_progress"}, "job": {}}]},
        {"assignmentId": "assignment-partial", "status": "submitted"},
    ]
    def opener(request, timeout):
        if request.full_url == "https://objects.example/recover":
            assert request.get_method() == "PUT" and request.data == content
            return FakeResponse({})
        return FakeResponse(responses.pop(0))
    result = retry_prepared_delivery("assignment-partial", database_path=db_path, lifecycle=NearMarketLifecycle("aat_test", opener=opener))
    assert result.status == "submitted"
    with sqlite3.connect(db_path) as db:
        state = db.execute("SELECT state FROM near_market_delivery_outbox WHERE assignment_id='assignment-partial'").fetchone()[0]
    assert state == "SUBMITTED"
