import json

from ownera.cli import main


def _payload():
    return json.dumps(
        [
            {
                "project": "CLI Example",
                "slug": "cli-example",
                "maxBounty": 10000,
                "programType": ["Smart Contract"],
                "projectType": ["DeFi"],
                "ecosystem": ["Ethereum"],
                "language": ["Solidity"],
                "kyc": False,
                "inviteOnly": False,
                "isPaused": False,
                "launchDate": "2026-01-01T00:00:00Z",
                "endDate": None,
                "assets": [{"url": "https://example.org/contracts", "type": "smart_contract"}],
                "rewards": [{"assetType": "smart_contract", "level": "critical", "payout": "1000-10000", "pocRequired": True}],
                "programOverview": "Bounded smart contract review.",
                "outOfScopeAndRules": "No production user testing.",
                "rewardsToken": "USD",
            }
        ]
    )


def test_cli_persists_candidates_and_repeat_run_reuses_evidence(tmp_path, capsys):
    payload_file = tmp_path / "catalog.json"
    payload_file.write_text(_payload(), encoding="utf-8")
    database = tmp_path / "data" / "ownera.sqlite3"
    args = [
        "discover-immunefi",
        "--database", str(database),
        "--payload-file", str(payload_file),
        "--format", "json",
    ]

    assert main(args) == 0
    first = json.loads(capsys.readouterr().out)
    assert first["candidate_count"] == 1
    assert first["candidates"][0]["status"] == "PENDING_OWNER_REVIEW"
    assert "not expected or guaranteed revenue" in first["limitations"][0]

    assert main(args) == 0
    second = json.loads(capsys.readouterr().out)
    assert second["candidates"][0]["opportunity_id"] == first["candidates"][0]["opportunity_id"]
    assert second["candidates"][0]["evidence_id"] == first["candidates"][0]["evidence_id"]

    import sqlite3

    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT COUNT(*) FROM opportunity_evidence").fetchone()[0] == 1


def test_cli_rejects_malformed_payload_without_reporting_success(tmp_path, capsys):
    payload_file = tmp_path / "bad.json"
    payload_file.write_text("not json", encoding="utf-8")
    result = main([
        "discover-immunefi",
        "--database", str(tmp_path / "ownera.sqlite3"),
        "--payload-file", str(payload_file),
        "--format", "json",
    ])
    captured = capsys.readouterr()
    assert result == 1
    assert "SourceAdapterError" in captured.err
    assert captured.out == ""


def test_rank_immunefi_returns_explainable_fit_not_expected_payout(tmp_path, capsys):
    payload_file = tmp_path / "catalog.json"
    payload_file.write_text(_payload(), encoding="utf-8")
    database = tmp_path / "rank.sqlite3"
    assert main([
        "discover-immunefi", "--database", str(database),
        "--payload-file", str(payload_file),
    ]) == 0
    capsys.readouterr()

    assert main([
        "rank-immunefi", "--database", str(database), "--format", "json",
    ]) == 0
    report = json.loads(capsys.readouterr().out)
    item = report["results"][0]
    assert item["project"] == "CLI Example"
    assert item["score"] > 0
    assert "solidity_skill_fit:+20" in item["reasons"]
    assert item["max_bounty_ceiling"] == "10000"
    assert all("ceiling" not in reason for reason in item["reasons"])
    assert "Not exploit probability" in report["scoring_notice"]


def test_rank_immunefi_excludes_invite_only_from_research_queue(tmp_path, capsys):
    payload = json.loads(_payload())
    payload[0]["inviteOnly"] = True
    payload_file = tmp_path / "invite.json"
    payload_file.write_text(json.dumps(payload), encoding="utf-8")
    database = tmp_path / "invite.sqlite3"
    assert main([
        "discover-immunefi", "--database", str(database),
        "--payload-file", str(payload_file),
    ]) == 0
    capsys.readouterr()
    assert main(["rank-immunefi", "--database", str(database), "--format", "json"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["result_count"] == 0


def test_discover_openradar_cli_reports_guest_feed_as_observed(monkeypatch, tmp_path, capsys):
    from datetime import datetime, timezone
    from uuid import uuid4

    from ownera.sources.openradar import DiscoveredGig

    class FakeAdapter:
        FEED_DELAY_HOURS = 12

        def __init__(self, registry):
            assert registry is not None

        def discover(self, *, limit):
            assert limit == 25
            return (DiscoveredGig(
                gig_id=uuid4(), evidence_id=uuid4(), title="Нужен Python developer",
                text="Ищу исполнителя для Python API",
                source_url="https://kwork.ru/projects/1",
                canonical_url="https://kwork.ru/projects/1",
                published_at=datetime(2026, 11, 1, tzinfo=timezone.utc),
                created_at=datetime(2026, 11, 1, tzinfo=timezone.utc),
                budget=None, currency=None, payment_period="fixed", skills=("Python",),
                source_platform="kwork", feed_score=70, relevance_score=42,
                relevance_reasons=("capability_match:python_backend",),
                buyer_intent="BUYER_REQUEST_SIGNAL", source_status="UNKNOWN",
                lifecycle_status="OBSERVED", contacts_available=False,
            ),)

    monkeypatch.setattr("ownera.cli.OpenRadarPublicFeedAdapter", FakeAdapter)
    database = tmp_path / "ownera.sqlite3"
    assert main([
        "discover-openradar", "--database", str(database),
        "--limit", "25", "--format", "json",
    ]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["candidate_count"] == 1
    assert report["feed_delay_hours"] == 12
    assert report["contacts_available"] is False
    assert report["candidates"][0]["source_status"] == "UNKNOWN"
    assert report["candidates"][0]["lifecycle_status"] == "OBSERVED"
