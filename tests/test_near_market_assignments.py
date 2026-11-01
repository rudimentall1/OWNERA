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
