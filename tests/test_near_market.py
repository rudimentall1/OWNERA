from ownera.near_market import sync_paid_work
from ownera.paid_work import PaidWorkPipeline


def _job(job_id="job-1", status="open", budget="15", currency="USDC"):
    return {
        "jobId": job_id,
        "title": "Python API research",
        "description": "Research an API integration using Python.",
        "status": status,
        "budgetAmount": budget,
        "budgetToken": currency,
        "tags": ["python", "api"],
        "isPrivate": False,
    }


def test_sync_imports_open_jobs_into_paid_work_and_is_idempotent(tmp_path):
    db = tmp_path / "ownera.sqlite3"
    first = sync_paid_work(db, jobs=[_job()])
    assert (first.fetched, first.created, first.unchanged) == (1, 1, 0)
    item = PaidWorkPipeline(db).opportunities[0]
    assert item.currency == "USDC"
    assert item.required_capabilities == frozenset({"python", "api_integration", "research"})
    second = sync_paid_work(db, jobs=[_job()])
    assert second.created == 0 and second.unchanged == 1


def test_sync_ignores_closed_private_and_invalid_budget_jobs(tmp_path):
    jobs = [
        _job("closed", "closed"),
        {**_job("private"), "isPrivate": True},
        _job("bad", budget="not-money"),
        {**_job("reject"), "title": "Sentinel REJECT TEST", "description": "Must reject this test"},
    ]
    report = sync_paid_work(tmp_path / "ownera.sqlite3", jobs=jobs)
    assert report.created == 0
    assert report.ignored == 4


def test_sync_reports_changed_terms_without_overwriting_existing_record(tmp_path):
    db = tmp_path / "ownera.sqlite3"
    sync_paid_work(db, jobs=[_job()])
    report = sync_paid_work(db, jobs=[_job(budget="25")])
    assert report.conflicts == ("job-1",)
    assert PaidWorkPipeline(db).opportunities[0].budget_max == 15
