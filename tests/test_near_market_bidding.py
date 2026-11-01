from datetime import datetime, timezone
from decimal import Decimal

import pytest

from ownera.near_market_bidding import (
    BidPolicy,
    generate_proposal,
    qualify_job,
    run_bid_cycle,
)


def _job(**overrides):
    job = {
        "jobId": "job-1",
        "title": "Micro-job economics research",
        "description": "Prepare a research report with a cost model, source citations and recommendations.",
        "tags": ["research"],
        "status": "open",
        "jobKind": "standard",
        "budgetAmount": "15",
        "budgetToken": "USDC",
        "currentMaxSlots": 2,
        "acceptanceWindowDays": 3,
        "minBuilderVerification": "none",
        "requiresVerifiable": False,
        "isPrivate": False,
        "createdAt": "2026-10-12T09:58:17Z",
    }
    return {**job, **overrides}


def test_qualifies_bounded_usdc_research_job():
    eligible, reasons = qualify_job(
        _job(),
        BidPolicy(),
        now=datetime(2026, 11, 1, tzinfo=timezone.utc),
    )
    assert eligible
    assert reasons == ()


@pytest.mark.parametrize(
    ("changes", "reason"),
    [
        ({"budgetToken": "USD"}, "unsupported_payment_rail"),
        ({"budgetAmount": "100"}, "budget_outside_policy"),
        ({"minBuilderVerification": "verified"}, "builder_verification_required"),
        ({"requiresVerifiable": True}, "verifiable_delivery_required"),
        ({"currentMaxSlots": 0}, "no_slots_available"),
        ({"acceptanceWindowDays": 14}, "acceptance_window_outside_policy"),
        ({"acceptanceWindowDays": None}, "missing_or_invalid_acceptance_window"),
        ({"status": "closed"}, "job_not_open"),
        ({"title": "Book a hotel", "description": "Travel booking", "tags": ["research"]},
         "external_side_effect_or_restricted_scope"),
        ({"createdAt": "2026-08-01T00:00:00Z"}, "listing_too_old"),
    ],
)
def test_policy_rejects_jobs_outside_bounded_scope(changes, reason):
    eligible, reasons = qualify_job(
        _job(**changes),
        BidPolicy(),
        now=datetime(2026, 11, 1, tzinfo=timezone.utc),
    )
    assert not eligible
    assert reason in reasons


def test_dry_run_never_submits_and_skips_already_bid_jobs(tmp_path):
    report = run_bid_cycle(
        tmp_path / "ownera.sqlite3",
        policy=BidPolicy(max_total_commitments=2),
        dry_run=True,
        jobs=[_job(), _job(jobId="job-2")],
        bids=[{"jobId": "job-1", "status": "pending"}],
        assignments=[],
    )
    assert report["mode"] == "dry_run"
    assert report["eligible"] == [
        {"job_id": "job-2", "title": "Micro-job economics research", "amount": "15", "currency": "USDC"}
    ]
    assert report["submitted"] == []
    assert any(x.get("reason") == "already_bid" for x in report["skipped"])


def test_pending_and_active_limits_fail_closed(tmp_path):
    pending = run_bid_cycle(
        tmp_path / "ownera.sqlite3",
        policy=BidPolicy(max_pending_bids=1, max_total_commitments=3),
        dry_run=True,
        jobs=[_job()],
        bids=[{"jobId": "other", "status": "pending"}],
        assignments=[],
    )
    assert pending["eligible"] == []
    assert pending["skipped"][0]["reason"] == "pending_bid_limit_reached"

    active = run_bid_cycle(
        tmp_path / "ownera.sqlite3",
        policy=BidPolicy(max_active_assignments=1),
        dry_run=True,
        jobs=[_job()],
        bids=[],
        assignments=[{"assignment": {"status": "in_progress"}}],
    )
    assert active["eligible"] == []
    assert active["skipped"][0]["reason"] == "active_assignment_limit_reached"

    total = run_bid_cycle(
        tmp_path / "ownera.sqlite3",
        policy=BidPolicy(max_total_commitments=1),
        dry_run=True,
        jobs=[_job()],
        bids=[{"jobId": "other", "status": "pending"}],
        assignments=[],
    )
    assert total["eligible"] == []
    assert total["skipped"][0]["reason"] == "total_commitment_limit_reached"


def test_live_bidding_requires_explicit_enable_flag(tmp_path):
    with pytest.raises(PermissionError, match="disabled"):
        run_bid_cycle(
            tmp_path / "ownera.sqlite3",
            policy=BidPolicy(enabled=False),
            dry_run=False,
            jobs=[_job()],
            bids=[],
            assignments=[],
        )


def test_proposal_generation_is_deterministic_and_task_specific():
    proposal = generate_proposal(_job(), Decimal("15"))
    assert proposal.startswith("Bid: 15 USDC.")
    assert "1,000–2,500-word English Markdown report" in proposal
    assert "Stripe pricing" in proposal
    assert "Coinbase x402 docs" in proposal
    assert "published prices from assumptions" in proposal


def test_live_cycle_submits_only_policy_bounded_bid_and_audits_it(tmp_path, monkeypatch):
    calls = []

    def fake_request(method, path, token, payload=None):
        calls.append((method, path, token, payload))
        return {"bidId": "bid-1", "status": "pending"}

    monkeypatch.setattr("ownera.near_market_bidding._request_json", fake_request)
    report = run_bid_cycle(
        tmp_path / "ownera.sqlite3",
        policy=BidPolicy(enabled=True, max_submissions_per_run=1),
        token="test-token",
        dry_run=False,
        jobs=[_job()],
        bids=[],
        assignments=[],
        proposal_factory=lambda job, amount: f"Bid: {amount} USDC. I will deliver the research report.",
    )

    assert calls == [
        (
            "POST",
            "/v1/jobs/job-1/bids",
            "test-token",
            {"amount": "15", "proposal": "Bid: 15 USDC. I will deliver the research report."},
        )
    ]
    assert report["submitted"] == [
        {"job_id": "job-1", "title": "Micro-job economics research", "amount": "15", "currency": "USDC", "bid_id": "bid-1", "status": "pending"}
    ]
    import sqlite3

    with sqlite3.connect(tmp_path / "ownera.sqlite3") as db:
        row = db.execute("SELECT bid_id, job_id, amount, status FROM near_market_bid_audit").fetchone()
    assert row == ("bid-1", "job-1", "15", "pending")
