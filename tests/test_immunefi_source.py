import json
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest

from ownera.evidence_registry import (
    EvidenceStatus,
    SQLiteOpportunityEvidenceRegistry,
)
from ownera.owner_control import AuthenticatedPrincipal
from ownera.sources.immunefi import (
    IMMUNEFI_CATALOG_URL,
    ImmunefiPublicCatalogAdapter,
    SourceAdapterError,
)


class FakeEvidenceRegistry:
    def __init__(self):
        self.records = []

    def capture(self, **kwargs):
        evidence_id = uuid4()
        self.records.append({**kwargs, "evidence_id": evidence_id})
        return SimpleNamespace(evidence_id=evidence_id)


def _record(**overrides):
    record = {
        "project": "Example Protocol",
        "slug": "example-protocol",
        "maxBounty": 250000,
        "programType": ["Smart Contract"],
        "projectType": ["DeFi"],
        "ecosystem": ["Ethereum", "Arbitrum"],
        "language": ["Solidity"],
        "kyc": False,
        "inviteOnly": False,
        "isPaused": False,
        "launchDate": "2026-01-01T00:00:00.000Z",
        "endDate": None,
        "assets": [
            {"url": "https://example.org/contracts", "type": "smart_contract"}
        ],
        "rewards": [
            {
                "assetType": "smart_contract",
                "level": "critical",
                "payout": "100000-250000",
                "pocRequired": True,
            }
        ],
        "programOverview": "Review the protocol contracts.",
        "outOfScopeAndRules": "Do not test production users.",
        "rewardsToken": "USD",
    }
    record.update(overrides)
    return record


def test_ingest_captures_only_active_public_programs_as_pending_evidence():
    registry = FakeEvidenceRegistry()
    adapter = ImmunefiPublicCatalogAdapter(registry)
    now = datetime(2026, 11, 1, tzinfo=timezone.utc)
    records = [
        _record(),
        _record(project="Paused", slug="paused", isPaused=True),
        _record(project="Private", slug="private", inviteOnly=True),
        _record(project="Future", slug="future", launchDate="2027-01-01T00:00:00Z"),
        _record(project="Ended", slug="ended", endDate="2026-10-31T00:00:00Z"),
    ]

    candidates = adapter.ingest(json.dumps(records).encode(), now=now)

    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.project == "Example Protocol"
    assert candidate.source_url == "https://immunefi.com/bug-bounty/example-protocol/"
    assert candidate.max_bounty_ceiling == 250000
    assert candidate.kyc_required is False
    assert candidate.assets_count == 1
    assert candidate.captured_at == now
    assert len(registry.records) == 1
    evidence = registry.records[0]
    assert evidence["opportunity_id"] == candidate.opportunity_id
    assert evidence["source_url"] == candidate.source_url
    assert evidence["source_name"] == "Immunefi public bounty catalog"
    snapshot = json.loads(evidence["content_snapshot"])
    assert snapshot["source"] == IMMUNEFI_CATALOG_URL
    assert snapshot["max_bounty_ceiling"] == 250000


def test_maximum_bounty_is_explicitly_a_ceiling_not_a_budget_floor():
    registry = FakeEvidenceRegistry()
    candidate = ImmunefiPublicCatalogAdapter(registry).ingest(
        json.dumps([_record()]).encode(),
        now=datetime(2026, 11, 1, tzinfo=timezone.utc),
    )[0]

    assert candidate.max_bounty_ceiling == 250000
    assert not hasattr(candidate, "budget_min")
    assert not hasattr(candidate, "guaranteed_revenue")


@pytest.mark.parametrize(
    "payload",
    [
        b"{not-json}",
        b'{"not":"a-list"}',
        json.dumps([{"project": "missing required flags"}]).encode(),
    ],
)
def test_ingest_rejects_invalid_or_drifted_catalog_schema(payload):
    adapter = ImmunefiPublicCatalogAdapter(FakeEvidenceRegistry())

    with pytest.raises(SourceAdapterError):
        adapter.ingest(payload, now=datetime(2026, 11, 1, tzinfo=timezone.utc))


def test_ingest_rejects_naive_capture_time():
    adapter = ImmunefiPublicCatalogAdapter(FakeEvidenceRegistry())

    with pytest.raises(ValueError, match="timezone-aware"):
        adapter.ingest(
            json.dumps([_record()]).encode(),
            now=datetime(2026, 11, 1),
        )


def test_ingest_does_not_capture_when_record_identity_is_invalid():
    registry = FakeEvidenceRegistry()
    adapter = ImmunefiPublicCatalogAdapter(registry)

    with pytest.raises(SourceAdapterError, match="project identity"):
        adapter.ingest(
            json.dumps([_record(slug="../attacker")]).encode(),
            now=datetime(2026, 11, 1, tzinfo=timezone.utc),
        )

    assert registry.records == []


class OwnerAuthenticator:
    def authenticate(self, credential):
        if credential != "owner-token":
            raise ValueError("invalid credential")
        now = datetime.now(timezone.utc)
        return AuthenticatedPrincipal(
            issuer="test-issuer",
            subject="owner-1",
            roles=frozenset({"owner:commercial"}),
            authenticated_at=now,
            expires_at=now.replace(year=now.year + 1),
            authentication_method="test",
            session_id="source-adapter-test",
        )


def test_live_adapter_ingestion_writes_pending_evidence_to_real_registry(tmp_path):
    registry = SQLiteOpportunityEvidenceRegistry(
        tmp_path / "evidence.db", OwnerAuthenticator()
    )
    adapter = ImmunefiPublicCatalogAdapter(registry)
    candidates = adapter.ingest(
        json.dumps([_record()]).encode(),
        now=datetime(2026, 11, 1, tzinfo=timezone.utc),
    )

    assert len(candidates) == 1
    evidence = registry.get(candidates[0].evidence_id)
    assert evidence.opportunity_id == candidates[0].opportunity_id
    assert evidence.status is EvidenceStatus.PENDING
    assert registry.verify(evidence.evidence_id)


def test_repeated_import_is_idempotent_and_ignores_observation_timestamp(tmp_path):
    registry = SQLiteOpportunityEvidenceRegistry(
        tmp_path / "dedupe.db", OwnerAuthenticator()
    )
    adapter = ImmunefiPublicCatalogAdapter(registry)
    first = adapter.ingest(
        json.dumps([_record()]).encode(),
        now=datetime(2026, 11, 1, tzinfo=timezone.utc),
    )[0]
    second = adapter.ingest(
        json.dumps([_record()]).encode(),
        now=datetime(2026, 11, 2, tzinfo=timezone.utc),
    )[0]

    assert second.opportunity_id == first.opportunity_id
    assert second.evidence_id == first.evidence_id
    assert second.captured_at == first.captured_at
    connection = registry._connect()
    try:
        assert connection.execute("SELECT COUNT(*) FROM opportunity_evidence").fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM opportunity_evidence_events").fetchone()[0] == 1
    finally:
        connection.close()
    assert registry.verify(first.evidence_id)


def test_changed_program_terms_create_new_pending_evidence_version(tmp_path):
    registry = SQLiteOpportunityEvidenceRegistry(
        tmp_path / "versions.db", OwnerAuthenticator()
    )
    adapter = ImmunefiPublicCatalogAdapter(registry)
    first = adapter.ingest(
        json.dumps([_record()]).encode(),
        now=datetime(2026, 11, 1, tzinfo=timezone.utc),
    )[0]
    changed = adapter.ingest(
        json.dumps([_record(maxBounty=300000)]).encode(),
        now=datetime(2026, 11, 2, tzinfo=timezone.utc),
    )[0]

    assert changed.opportunity_id == first.opportunity_id
    assert changed.evidence_id != first.evidence_id
    assert registry.get(first.evidence_id).status is EvidenceStatus.PENDING
    assert registry.get(changed.evidence_id).status is EvidenceStatus.PENDING
    assert registry.verify(first.evidence_id)
    assert registry.verify(changed.evidence_id)
    connection = registry._connect()
    try:
        assert connection.execute("SELECT COUNT(*) FROM opportunity_evidence").fetchone()[0] == 2
    finally:
        connection.close()


def test_lifecycle_updates_existing_source_and_reactivation_does_not_duplicate(tmp_path):
    registry = SQLiteOpportunityEvidenceRegistry(
        tmp_path / "lifecycle.db", OwnerAuthenticator()
    )
    adapter = ImmunefiPublicCatalogAdapter(registry)
    active = adapter.ingest(
        json.dumps([_record()]).encode(),
        now=datetime(2026, 11, 1, tzinfo=timezone.utc),
    )[0]

    adapter.ingest(
        json.dumps([_record(isPaused=True)]).encode(),
        now=datetime(2026, 11, 2, tzinfo=timezone.utc),
    )
    state = registry.source_observation("immunefi:example-protocol")
    assert state["lifecycle_status"] == "PAUSED"

    reactivated = adapter.ingest(
        json.dumps([_record()]).encode(),
        now=datetime(2026, 11, 3, tzinfo=timezone.utc),
    )[0]
    assert reactivated.opportunity_id == active.opportunity_id
    assert reactivated.evidence_id == active.evidence_id
    assert registry.source_observation("immunefi:example-protocol")["lifecycle_status"] == "ACTIVE"
    connection = registry._connect()
    try:
        assert connection.execute("SELECT COUNT(*) FROM opportunity_evidence").fetchone()[0] == 1
    finally:
        connection.close()


def test_inactive_listing_never_seen_active_does_not_create_opportunity(tmp_path):
    registry = SQLiteOpportunityEvidenceRegistry(
        tmp_path / "inactive.db", OwnerAuthenticator()
    )
    adapter = ImmunefiPublicCatalogAdapter(registry)
    assert adapter.ingest(
        json.dumps([_record(isPaused=True)]).encode(),
        now=datetime(2026, 11, 1, tzinfo=timezone.utc),
    ) == ()
    assert registry.source_observation("immunefi:example-protocol") is None



def test_reverting_terms_creates_a_new_version_without_idempotency_collision(tmp_path):
    registry = SQLiteOpportunityEvidenceRegistry(
        tmp_path / "revert.db", OwnerAuthenticator()
    )
    adapter = ImmunefiPublicCatalogAdapter(registry)
    initial = adapter.ingest(
        json.dumps([_record(maxBounty=250000)]).encode(),
        now=datetime(2026, 11, 1, tzinfo=timezone.utc),
    )[0]
    changed = adapter.ingest(
        json.dumps([_record(maxBounty=300000)]).encode(),
        now=datetime(2026, 11, 2, tzinfo=timezone.utc),
    )[0]
    reverted = adapter.ingest(
        json.dumps([_record(maxBounty=250000)]).encode(),
        now=datetime(2026, 11, 3, tzinfo=timezone.utc),
    )[0]

    assert len({initial.evidence_id, changed.evidence_id, reverted.evidence_id}) == 3
    assert initial.opportunity_id == changed.opportunity_id == reverted.opportunity_id
    assert registry.verify(initial.evidence_id)
    assert registry.verify(changed.evidence_id)
    assert registry.verify(reverted.evidence_id)
