from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from ownera.commercial import (
    CommercialAssessment,
    CommercialEngine,
    CommercialError,
    CommercialOpportunity,
    OpportunityStatus,
    ProposalDraft,
    ProposalStatus,
)


def _opportunity(**overrides):
    values = {
        "title": "Build a FastAPI integration",
        "description": "Implement a bounded API integration with tests.",
        "source_name": "Kwork",
        "source_url": "https://kwork.ru/projects/123",
        "budget_min": Decimal("600"),
        "budget_max": Decimal("800"),
        "currency": "RUB",
        "required_capabilities": frozenset({"python", "fastapi"}),
        "evidence_refs": ("https://kwork.ru/projects/123",),
        "deadline": datetime.now(timezone.utc) + timedelta(days=5),
    }
    values.update(overrides)
    return CommercialOpportunity(**values)


def _assessment(opportunity, **overrides):
    values = {
        "opportunity_id": opportunity.opportunity_id,
        "estimated_delivery_cost": Decimal("250"),
        "platform_fee_rate": Decimal("0.10"),
        "contingency_rate": Decimal("0.10"),
        "win_probability": Decimal("0.50"),
        "minimum_net_margin": Decimal("0.20"),
        "terms_reviewed": True,
        "eligibility_confirmed": True,
    }
    values.update(overrides)
    return CommercialAssessment(**values)


def test_qualified_opportunity_uses_conservative_budget_floor():
    engine = CommercialEngine()
    opportunity = _opportunity()
    engine.add_opportunity(opportunity)

    result = engine.assess(_assessment(opportunity))

    assert result.status is OpportunityStatus.QUALIFIED
    assert result.conservative_revenue == Decimal("600")
    assert result.expected_net_profit == Decimal("295.00")
    assert result.expected_net_margin == Decimal("295.00") / Decimal("600")


def test_missing_terms_or_eligibility_requires_review():
    engine = CommercialEngine()
    opportunity = _opportunity()
    engine.add_opportunity(opportunity)

    result = engine.assess(
        _assessment(opportunity, terms_reviewed=False, eligibility_confirmed=False)
    )

    assert result.status is OpportunityStatus.NEEDS_REVIEW
    assert "terms_not_reviewed" in result.reasons
    assert "eligibility_not_confirmed" in result.reasons


def test_unprofitable_opportunity_is_rejected():
    engine = CommercialEngine()
    opportunity = _opportunity(budget_min=Decimal("200"))
    engine.add_opportunity(opportunity)

    result = engine.assess(_assessment(opportunity))

    assert result.status is OpportunityStatus.REJECTED
    assert "non_positive_expected_net_profit" in result.reasons


def test_expired_opportunity_is_rejected():
    engine = CommercialEngine()
    opportunity = _opportunity(deadline=datetime.now(timezone.utc) - timedelta(days=1))
    engine.add_opportunity(opportunity)

    result = engine.assess(_assessment(opportunity))

    assert result.status is OpportunityStatus.REJECTED
    assert "deadline_expired" in result.reasons


def test_proposal_requires_qualified_opportunity_and_owner_approval():
    engine = CommercialEngine()
    opportunity = _opportunity()
    engine.add_opportunity(opportunity)
    engine.assess(_assessment(opportunity))

    proposal = ProposalDraft(
        opportunity_id=opportunity.opportunity_id,
        scope="Implement the API integration and automated tests.",
        acceptance_criteria=("Endpoint works", "Tests pass"),
        delivery_plan=("Implement", "Test", "Prepare handover"),
        quote_amount=Decimal("600"),
        currency="RUB",
    )
    pending = engine.draft_proposal(proposal)
    assert pending.status is ProposalStatus.AWAITING_OWNER_APPROVAL

    with pytest.raises(CommercialError, match="only qualified"):
        engine.draft_proposal(
            ProposalDraft(
                opportunity_id=_opportunity().opportunity_id,
                scope="Invalid",
                acceptance_criteria=("Done",),
                delivery_plan=("Build",),
                quote_amount=Decimal("100"),
                currency="RUB",
            )
        )

    approved = engine.approve_proposal(pending.proposal_id, "owner")
    assert approved.status is ProposalStatus.APPROVED_FOR_SUBMISSION
    assert approved.owner_approved_by == "owner"


def test_proposal_cannot_be_approved_twice():
    engine = CommercialEngine()
    opportunity = _opportunity()
    engine.add_opportunity(opportunity)
    engine.assess(_assessment(opportunity))
    proposal = engine.draft_proposal(
        ProposalDraft(
            opportunity_id=opportunity.opportunity_id,
            scope="Implement integration",
            acceptance_criteria=("Tests pass",),
            delivery_plan=("Build", "Test"),
            quote_amount=Decimal("600"),
            currency="RUB",
        )
    )
    engine.approve_proposal(proposal.proposal_id, "owner")

    with pytest.raises(CommercialError, match="not awaiting"):
        engine.approve_proposal(proposal.proposal_id, "owner")
