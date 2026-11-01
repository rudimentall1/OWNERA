from ownera.near_market_assignments import sync_assignments


def test_assignment_intake_is_idempotent_and_tracks_updates(tmp_path):
    db = tmp_path / "ownera.sqlite3"
    row = {"assignmentId": "hire-1", "jobId": "job-9", "status": "assigned", "amount": "12"}
    first = sync_assignments(db, assignments=[row])
    assert (first.fetched, first.created, first.unchanged, first.ignored) == (1, 1, 0, 0)
    second = sync_assignments(db, assignments=[row])
    assert second.created == 0 and second.unchanged == 1
    third = sync_assignments(db, assignments=[{**row, "status": "in_progress"}])
    assert third.created == 1 and third.unchanged == 0


def test_assignment_intake_ignores_incomplete_records(tmp_path):
    rows = [
        {"assignmentId": "missing-job", "status": "assigned"},
        {"jobId": "missing-id", "status": "assigned"},
        {"assignmentId": "missing-status", "jobId": "job-1"},
    ]
    report = sync_assignments(tmp_path / "ownera.sqlite3", assignments=rows)
    assert report.fetched == 3
    assert report.created == 0
    assert report.ignored == 3


def test_assignment_intake_accepts_documented_nested_worker_payload(tmp_path):
    item = {
        "assignment": {"assignmentId": "hire-nested", "jobId": "job-nested", "status": "in_progress", "startedAt": None},
        "job": {"jobId": "job-nested", "title": "Build API", "description": "Implement API"},
        "latestMessage": None,
    }
    report = sync_assignments(tmp_path / "ownera.sqlite3", assignments=[item])
    assert report.created == 1 and report.ignored == 0


def test_fetch_assignments_requests_all_statuses_and_paginates(monkeypatch):
    import json
    from urllib.parse import parse_qs, urlparse

    from ownera import near_market_assignments as module

    calls = []
    class Response:
        def __init__(self, rows): self.rows = rows
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def read(self): return json.dumps({"assignments": self.rows}).encode()

    def opener(request, timeout):
        query = parse_qs(urlparse(request.full_url).query)
        calls.append(query)
        offset = int(query["offset"][0])
        rows = [{"assignment": {"assignmentId": f"a{i}", "jobId": f"j{i}", "status": "accepted"}} for i in range(offset, offset + 100)]
        if offset == 200:
            rows = [{"assignment": {"assignmentId": "a200", "jobId": "j200", "status": "accepted"}}]
        return Response(rows)

    rows = module.fetch_assignments("test-token", opener=opener)
    assert len(rows) == 201
    assert [int(call["offset"][0]) for call in calls] == [0, 100, 200]
    assert all(call["status"] == ["all"] and call["limit"] == ["100"] for call in calls)


def test_assignment_sync_prepares_deterministic_non_executable_research_plan(tmp_path):
    import json
    import sqlite3

    db = tmp_path / "ownera.sqlite3"
    item = {
        "assignment": {
            "assignmentId": "research-1",
            "jobId": "job-research-1",
            "status": "in_progress",
            "startedAt": "2026-11-01T12:00:00Z",
        },
        "job": {
            "jobId": "job-research-1",
            "title": "[internal research] Economics of micro-jobs on a marketplace with held payments and a judge",
            "description": "Deliver English Markdown. Cite every factual claim with a URL actually opened. Model $0.05, $0.20, $1 and $5.",
        },
    }

    first = sync_assignments(db, assignments=[item])
    assert first.plans_prepared == 1
    with sqlite3.connect(db) as connection:
        row = connection.execute(
            "SELECT plan_sha256,plan_json,state FROM near_market_assignment_plans WHERE assignment_id='research-1'"
        ).fetchone()
    plan = json.loads(row[1])
    assert row[0] == plan["plan_sha256"]
    assert row[2] == "PLAN_READY_NOT_EXECUTABLE"
    assert plan["plan_key"] == "micro_job_economics"
    assert plan["word_count"] == {"minimum": 1000, "maximum": 2500}
    assert "command" not in plan
    assert plan["execution_blockers"]


def test_assignment_sync_does_not_plan_unsupported_or_unstarted_assignments(tmp_path):
    import sqlite3

    db = tmp_path / "ownera.sqlite3"
    unsupported = {
        "assignment": {"assignmentId": "unknown-1", "jobId": "job-unknown", "status": "in_progress"},
        "job": {"jobId": "job-unknown", "title": "Build a video dubbing agent", "description": "Generate dubbed video."},
    }
    unstarted = {
        "assignment": {"assignmentId": "not-started-1", "jobId": "job-known", "status": "completed"},
        "job": {"jobId": "job-known", "title": "Find SageKai Agent", "description": "Find the exact public agent."},
    }
    report = sync_assignments(db, assignments=[unsupported, unstarted])
    assert report.plans_prepared == 0
    with sqlite3.connect(db) as connection:
        count = connection.execute("SELECT COUNT(*) FROM near_market_assignment_plans").fetchone()[0]
    assert count == 0
