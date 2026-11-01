import json

import pytest

from ownera.near_market import NearMarketError
from ownera.near_market_lifecycle import NearMarketLifecycle


class FakeResponse:
    def __init__(self, payload):
        self.payload = json.dumps(payload).encode()
    def __enter__(self): return self
    def __exit__(self, *args): return False
    def read(self): return self.payload


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
    responses = [
        {"startedAt": "2026-11-01T12:00:00Z"},
        {"assignmentId": "assignment-live", "status": "submitted", "submittedAt": "2026-11-01T12:01:00Z", "deliverableHash": "hash"},
    ]
    def opener(request, timeout):
        requests.append(request)
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
    submitted = json.loads(requests[1].data)
    assert requests[1].full_url.endswith(f"/v1/assignments/{assignment_id}/submit")
    assert "buyer-visible result" in submitted["deliverableMarkdown"]
    assert "Generated and verified" in submitted["deliverableMarkdown"]
