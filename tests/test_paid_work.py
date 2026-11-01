import json
from decimal import Decimal

import pytest

from ownera.cli import main
from ownera.paid_work import PaidWorkError, PaidWorkPipeline


def _listing():
    return {
        "title": "Build a Telegram notification bot",
        "description": "Create a small Python bot that posts alerts from a public API.",
        "source_name": "Kwork",
        "source_url": "https://kwork.ru/projects/987654",
        "budget_min": "12000",
        "budget_max": "18000",
        "currency": "RUB",
        "required_capabilities": ["python", "telegram", "api_integration"],
        "evidence_refs": ["https://kwork.ru/projects/987654"],
    }


def test_paid_work_ingest_is_persistent_and_idempotent(tmp_path):
    database = tmp_path / "ownera.sqlite3"
    first = PaidWorkPipeline(database)
    opportunity, created = first.ingest(_listing())
    assert created is True

    restarted = PaidWorkPipeline(database)
    duplicate, created_again = restarted.ingest(_listing())
    assert created_again is False
    assert duplicate.opportunity_id == opportunity.opportunity_id
    assert len(restarted.opportunities) == 1
    assert restarted.opportunities[0].status.value == "DISCOVERED"


def test_paid_work_rejects_same_source_with_changed_terms(tmp_path):
    pipeline = PaidWorkPipeline(tmp_path / "ownera.sqlite3")
    pipeline.ingest(_listing())
    changed = _listing()
    changed["budget_min"] = "15000"
    with pytest.raises(PaidWorkError, match="different terms"):
        pipeline.ingest(changed)


def test_paid_work_assessment_requires_manual_review_flags(tmp_path):
    pipeline = PaidWorkPipeline(tmp_path / "ownera.sqlite3")
    opportunity, _ = pipeline.ingest(_listing())
    result = pipeline.assess(
        opportunity.opportunity_id,
        delivery_cost=Decimal("5000"),
        platform_fee_rate=Decimal("0.10"),
        contingency_rate=Decimal("0.10"),
        win_probability=Decimal("0.50"),
        minimum_net_margin=Decimal("0.20"),
        terms_reviewed=False,
        eligibility_confirmed=False,
    )
    assert result.status.value == "NEEDS_REVIEW"
    assert "terms_not_reviewed" in result.reasons
    assert "eligibility_not_confirmed" in result.reasons


def test_paid_work_assessment_and_proposal_draft_persist(tmp_path):
    database = tmp_path / "ownera.sqlite3"
    pipeline = PaidWorkPipeline(database)
    opportunity, _ = pipeline.ingest(_listing())
    result = pipeline.assess(
        opportunity.opportunity_id,
        delivery_cost=Decimal("3000"),
        platform_fee_rate=Decimal("0.10"),
        contingency_rate=Decimal("0.10"),
        win_probability=Decimal("0.50"),
        minimum_net_margin=Decimal("0.20"),
        terms_reviewed=True,
        eligibility_confirmed=True,
    )
    assert result.status.value == "QUALIFIED"
    proposal = pipeline.draft_proposal({
        "opportunity_id": str(opportunity.opportunity_id),
        "scope": "Implement the Telegram bot and one API integration.",
        "acceptance_criteria": ["Bot receives API data", "Alert message is delivered", "Tests pass"],
        "delivery_plan": ["Implement", "Test", "Prepare handover"],
        "quote_amount": "12000",
        "currency": "RUB",
    })
    restored = PaidWorkPipeline(database)
    assert restored.proposals[0].proposal_id == proposal.proposal_id
    assert restored.proposals[0].status.value == "AWAITING_OWNER_APPROVAL"


def test_paid_work_cli_ingest_list_and_assess(tmp_path, capsys):
    database = tmp_path / "ownera.sqlite3"
    payload = tmp_path / "listing.json"
    payload.write_text(json.dumps(_listing()), encoding="utf-8")
    assert main(["paid-work", "ingest", "--database", str(database), "--payload-file", str(payload)]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["created"] is True
    opportunity_id = result["opportunity_id"]

    assert main(["paid-work", "list", "--database", str(database)]) == 0
    listing = json.loads(capsys.readouterr().out)
    assert listing["count"] == 1

    assert main([
        "paid-work", "assess", "--database", str(database),
        "--opportunity-id", opportunity_id,
        "--delivery-cost", "5000", "--platform-fee-rate", "0.1",
        "--contingency-rate", "0.1", "--win-probability", "0.5",
        "--minimum-net-margin", "0.2",
    ]) == 0
    assessment = json.loads(capsys.readouterr().out)
    assert assessment["status"] == "NEEDS_REVIEW"


def test_paid_work_ingest_requires_evidence_refs(tmp_path):
    payload = _listing()
    payload["evidence_refs"] = []
    with pytest.raises(ValueError, match="evidence"):
        PaidWorkPipeline(tmp_path / "ownera.sqlite3").ingest(payload)
