import json
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest

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
