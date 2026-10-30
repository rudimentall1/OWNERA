import sqlite3
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from ownera.commercial import (
    CommercialAssessment,
    CommercialOpportunity,
    OpportunityStatus,
    ProposalDraft,
    ProposalStatus,
)
from ownera.commercial_repository import (
    CommercialSnapshotConflict,
    CommercialSnapshotIntegrityError,
    SQLiteCommercialRepository,
)
from ownera.persistent_commercial import PersistentCommercialEngine


def _opportunity():
    return CommercialOpportunity(
        title="FastAPI integration",
        description="Implement a bounded integration.",
        source_name="Kwork",
        source_url="https://kwork.ru/projects/456",
        budget_min=Decimal("600"),
        budget_max=Decimal("800"),
        currency="RUB",
        required_capabilities=frozenset({"python", "fastapi"}),
        evidence_refs=("https://kwork.ru/projects/456",),
        deadline=datetime.now(timezone.utc) + timedelta(days=3),
    )


def _assessment(opportunity):
    return CommercialAssessment(
        opportunity_id=opportunity.opportunity_id,
        estimated_delivery_cost=Decimal("250"),
        platform_fee_rate=Decimal("0.10"),
        contingency_rate=Decimal("0.10"),
        win_probability=Decimal("0.6"),
        minimum_net_margin=Decimal("0.2"),
        terms_reviewed=True,
        eligibility_confirmed=True,
    )


def _proposal(opportunity):
    return ProposalDraft(
        opportunity_id=opportunity.opportunity_id,
        scope="Implement the integration.",
        acceptance_criteria=("Endpoint works", "Tests pass"),
        delivery_plan=("Implement", "Test", "Handover"),
        quote_amount=Decimal("600"),
        currency="RUB",
    )


def test_commercial_pipeline_survives_restart(tmp_path):
    database = tmp_path / "ownera.sqlite3"
    engine = PersistentCommercialEngine(str(database))
    opportunity = _opportunity()
    engine.add_opportunity(opportunity)
    result = engine.assess(_assessment(opportunity))
    proposal = engine.draft_proposal(_proposal(opportunity))
    approved = engine.approve_proposal(proposal.proposal_id, "owner-1")

    restored = PersistentCommercialEngine(str(database))

    assert restored.version == 4
    assert restored.opportunities[0].status is OpportunityStatus.QUALIFIED
    assert restored.proposals[0].status is ProposalStatus.APPROVED_FOR_SUBMISSION
    assert restored.proposals[0].owner_approved_by == "owner-1"
    events = restored.repository.event_store.load("commercial_pipeline", "primary")
    assert [event.event_type for event in events] == [
        "OpportunityDiscovered", "OpportunityAssessed",
        "ProposalDrafted", "ProposalOwnerApproved",
    ]
    assert restored.repository.event_store.verify("commercial_pipeline", "primary")
    assert restored.proposals[0].proposal_id == approved.proposal_id
    assert result.expected_net_profit == Decimal("265.00")


def test_stale_commercial_writer_is_rejected_and_reloaded(tmp_path):
    database = tmp_path / "ownera.sqlite3"
    first = PersistentCommercialEngine(str(database))
    stale = PersistentCommercialEngine(str(database))
    first.add_opportunity(_opportunity())

    with pytest.raises(CommercialSnapshotConflict):
        stale.add_opportunity(_opportunity())

    assert stale.version == first.version
    assert len(stale.opportunities) == 1


def test_commercial_snapshot_digest_tampering_is_detected(tmp_path):
    database = tmp_path / "ownera.sqlite3"
    engine = PersistentCommercialEngine(str(database))
    engine.add_opportunity(_opportunity())

    connection = sqlite3.connect(database)
    connection.execute(
        "UPDATE commercial_snapshots SET payload_json = ? WHERE snapshot_id = 'primary'",
        ('{"schema_version":1,"opportunities":[]}',),
    )
    connection.commit()
    connection.close()

    with pytest.raises(CommercialSnapshotIntegrityError):
        SQLiteCommercialRepository(database).load()


def test_empty_commercial_repository_starts_at_version_zero(tmp_path):
    engine = PersistentCommercialEngine(str(tmp_path / "empty.sqlite3"))
    assert engine.version == 0
    assert engine.opportunities == ()
    assert engine.proposals == ()



def test_event_and_commercial_snapshot_roll_back_together_on_event_conflict(tmp_path):
    from ownera.event_store import ConcurrencyError

    database = tmp_path / "ownera.sqlite3"
    engine = PersistentCommercialEngine(str(database))
    opportunity = _opportunity()
    engine.add_opportunity(opportunity)

    before_snapshot = engine.version
    before_events = len(
        engine.repository.event_store.load("commercial_pipeline", "primary")
    )
    engine.repository.event_store.append(
        aggregate_type="commercial_pipeline",
        aggregate_id="primary",
        event_type="ExternalUnexpectedEvent",
        payload={"reason": "test conflict"},
        expected_version=before_events,
        idempotency_key="external-unexpected-event",
    )

    with pytest.raises(ConcurrencyError):
        engine.assess(_assessment(opportunity))

    restored = PersistentCommercialEngine(str(database))
    assert restored.version == before_snapshot
    assert len(restored.opportunities) == 1
    assert len(
        restored.repository.event_store.load("commercial_pipeline", "primary")
    ) == before_events + 1
    assert restored.opportunities[0].status is OpportunityStatus.DISCOVERED
