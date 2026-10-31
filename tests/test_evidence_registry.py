from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import pytest

from ownera.commercial import (
    CommercialAssessment,
    CommercialOpportunity,
    OpportunityStatus,
)
from ownera.evidence_registry import (
    EvidenceIntegrityError,
    EvidenceRegistryError,
    EvidenceStatus,
    SQLiteOpportunityEvidenceRegistry,
)
from ownera.owner_control import AuthenticatedPrincipal, OwnerControlError
from ownera.persistent_commercial import PersistentCommercialEngine


class StaticAuthenticator:
    def __init__(self, roles=frozenset({"owner:commercial"})):
        self.roles = roles

    def authenticate(self, credential):
        if credential != "valid":
            raise ValueError("invalid credential")
        now = datetime.now(timezone.utc)
        return AuthenticatedPrincipal(
            issuer="test-issuer",
            subject="owner-1",
            roles=self.roles,
            authenticated_at=now,
            expires_at=now + timedelta(minutes=5),
            authentication_method="test",
            session_id="session-1",
        )


@pytest.fixture
def registry(tmp_path: Path):
    return SQLiteOpportunityEvidenceRegistry(
        tmp_path / "evidence.db", StaticAuthenticator()
    )


def _capture(registry, opportunity_id=None):
    return registry.capture(
        opportunity_id=opportunity_id or uuid4(),
        source_name="Public bounty board",
        source_url="https://example.com/bounty/42",
        content_snapshot="Scope: review API authorization. Reward: 500 EUR.",
    )


def test_evidence_is_persisted_as_pending_with_content_digest(registry):
    item = _capture(registry)

    assert item.status is EvidenceStatus.PENDING
    assert item.content_sha256
    assert item.reviewed_by is None
    assert registry.verify(item.evidence_id)


def test_capture_rejects_non_https_and_oversized_snapshots(registry):
    with pytest.raises(ValueError, match="HTTPS"):
        registry.capture(
            opportunity_id=uuid4(),
            source_name="board",
            source_url="http://example.com/item",
            content_snapshot="listing",
        )
    with pytest.raises(ValueError, match="maximum"):
        registry.capture(
            opportunity_id=uuid4(),
            source_name="board",
            source_url="https://example.com/item",
            content_snapshot="x" * (registry.MAX_SNAPSHOT_CHARS + 1),
        )


def test_owner_review_accepts_evidence_and_binds_actor(registry):
    item = _capture(registry)

    reviewed = registry.review(
        "valid", item.evidence_id, accept=True, note="Terms and eligibility checked."
    )

    assert reviewed.status is EvidenceStatus.ACCEPTED
    assert reviewed.reviewed_by == "owner-1"
    assert reviewed.reviewed_at is not None
    assert registry.verify(item.evidence_id)


def test_review_requires_owner_commercial_role(tmp_path):
    registry = SQLiteOpportunityEvidenceRegistry(
        tmp_path / "evidence.db", StaticAuthenticator(frozenset({"owner:settlement"}))
    )
    item = _capture(registry)

    with pytest.raises(OwnerControlError, match="commercial review"):
        registry.review("valid", item.evidence_id, accept=True)


def test_review_rejects_invalid_credentials(registry):
    item = _capture(registry)

    with pytest.raises(OwnerControlError, match="authentication failed"):
        registry.review("wrong", item.evidence_id, accept=True)


def test_only_accepted_evidence_for_same_opportunity_passes_gate(registry):
    opportunity_id = uuid4()
    item = _capture(registry, opportunity_id)

    with pytest.raises(EvidenceRegistryError, match="not been accepted"):
        registry.require_accepted(opportunity_id, (str(item.evidence_id),))

    registry.review("valid", item.evidence_id, accept=True)
    registry.require_accepted(opportunity_id, (str(item.evidence_id),))

    with pytest.raises(EvidenceRegistryError, match="different opportunity"):
        registry.require_accepted(uuid4(), (str(item.evidence_id),))


def test_gate_rejects_url_refs_and_unknown_evidence_ids(registry):
    with pytest.raises(EvidenceRegistryError, match="UUIDs"):
        registry.require_accepted(uuid4(), ("https://example.com/listing",))
    with pytest.raises(EvidenceRegistryError, match="does not exist"):
        registry.require_accepted(uuid4(), (str(uuid4()),))


def test_rejected_evidence_never_passes_gate(registry):
    opportunity_id = uuid4()
    item = _capture(registry, opportunity_id)
    registry.review("valid", item.evidence_id, accept=False, note="Eligibility unclear.")

    with pytest.raises(EvidenceRegistryError, match="not been accepted"):
        registry.require_accepted(opportunity_id, (str(item.evidence_id),))


def test_evidence_cannot_be_reviewed_twice(registry):
    item = _capture(registry)
    registry.review("valid", item.evidence_id, accept=True)

    with pytest.raises(EvidenceRegistryError, match="only pending"):
        registry.review("valid", item.evidence_id, accept=False)


def test_verify_detects_content_row_tampering(registry):
    item = _capture(registry)
    connection = registry._connect()
    try:
        connection.execute(
            "UPDATE opportunity_evidence SET content_snapshot=? WHERE evidence_id=?",
            ("tampered listing", str(item.evidence_id)),
        )
    finally:
        connection.close()

    with pytest.raises(EvidenceIntegrityError, match="content digest"):
        registry.verify(item.evidence_id)


def test_verify_detects_event_chain_tampering(registry):
    item = _capture(registry)
    connection = registry._connect()
    try:
        connection.execute(
            "UPDATE opportunity_evidence_events SET event_type='Forged' WHERE evidence_id=?",
            (str(item.evidence_id),),
        )
    finally:
        connection.close()

    with pytest.raises(EvidenceIntegrityError, match="event hash"):
        registry.verify(item.evidence_id)


def test_review_rejects_future_timestamp(registry):
    item = _capture(registry)
    with pytest.raises(ValueError, match="future"):
        registry.review(
            "valid",
            item.evidence_id,
            accept=True,
            now=datetime.now(timezone.utc) + timedelta(minutes=1),
        )


def test_verify_detects_source_metadata_row_tampering(registry):
    item = _capture(registry)
    connection = registry._connect()
    try:
        connection.execute(
            "UPDATE opportunity_evidence SET source_url=? WHERE evidence_id=?",
            ("https://attacker.example/forged", str(item.evidence_id)),
        )
    finally:
        connection.close()

    with pytest.raises(EvidenceIntegrityError, match="capture event"):
        registry.verify(item.evidence_id)


def test_verify_detects_review_identity_row_tampering(registry):
    item = _capture(registry)
    registry.review("valid", item.evidence_id, accept=True)
    connection = registry._connect()
    try:
        connection.execute(
            "UPDATE opportunity_evidence SET reviewed_by=? WHERE evidence_id=?",
            ("forged-reviewer", str(item.evidence_id)),
        )
    finally:
        connection.close()

    with pytest.raises(EvidenceIntegrityError, match="review event"):
        registry.verify(item.evidence_id)


def test_persistent_qualification_requires_accepted_registry_evidence(tmp_path):
    database = tmp_path / "ownera.db"
    registry = SQLiteOpportunityEvidenceRegistry(database, StaticAuthenticator())
    opportunity_id = uuid4()
    evidence = _capture(registry, opportunity_id)
    opportunity = CommercialOpportunity(
        opportunity_id=opportunity_id,
        title="Paid API security review",
        description="Review a bounded API authorization scope.",
        source_name="Public bounty board",
        source_url="https://example.com/bounty/42",
        budget_min=Decimal("500"),
        budget_max=Decimal("700"),
        currency="EUR",
        required_capabilities=frozenset({"python", "security"}),
        evidence_refs=(str(evidence.evidence_id),),
    )
    assessment = CommercialAssessment(
        opportunity_id=opportunity_id,
        estimated_delivery_cost=Decimal("100"),
        platform_fee_rate=Decimal("0.10"),
        contingency_rate=Decimal("0.10"),
        win_probability=Decimal("0.50"),
        minimum_net_margin=Decimal("0.20"),
        terms_reviewed=True,
        eligibility_confirmed=True,
    )
    commercial = PersistentCommercialEngine(str(database), evidence_gate=registry)
    commercial.add_opportunity(opportunity)

    pending = commercial.assess(assessment)
    assert pending.status is OpportunityStatus.NEEDS_REVIEW
    assert "evidence_not_owner_accepted" in pending.reasons

    registry.review("valid", evidence.evidence_id, accept=True)
    accepted = commercial.assess(assessment)
    assert accepted.status is OpportunityStatus.QUALIFIED
    assert "evidence_not_owner_accepted" not in accepted.reasons

    restarted = PersistentCommercialEngine(str(database), evidence_gate=registry)
    restored_result = restarted.assess(assessment)
    assert restored_result.status is OpportunityStatus.QUALIFIED
