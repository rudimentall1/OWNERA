"""CLI for evidence-backed discovery and manual-first OWNERA paid-work operations.

Discovery commands are read-only apart from evidence capture. Paid-work commands
persist opportunity, assessment, and proposal state in the commercial SQLite store.
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from pathlib import Path

from ownera.evidence_registry import SQLiteOpportunityEvidenceRegistry
from ownera.near_market import sync_paid_work
from ownera.near_market_assignments import sync_assignments
from ownera.opportunity_intelligence import rank_immunefi
from ownera.paid_work import PaidWorkPipeline
from ownera.revenue_scout import LocalOllamaRevenueScout
from ownera.sources.immunefi import ImmunefiPublicCatalogAdapter
from ownera.sources.openradar import OpenRadarPublicFeedAdapter


class _NoOwnerAuthentication:
    """Discovery does not need owner privileges; review operations still fail closed."""

    def authenticate(self, credential: str):
        raise PermissionError("owner authentication is not configured for this CLI")


def _discover_immunefi(args: argparse.Namespace) -> int:
    database_path = Path(args.database)
    database_path.parent.mkdir(parents=True, exist_ok=True)
    registry = SQLiteOpportunityEvidenceRegistry(
        database_path, authenticator=_NoOwnerAuthentication()
    )
    adapter = ImmunefiPublicCatalogAdapter(registry)
    if args.payload_file:
        payload = Path(args.payload_file).read_bytes()
        candidates = adapter.ingest(payload)
        source_mode = "payload_file"
    else:
        candidates = adapter.discover()
        source_mode = "live_public_catalog"

    report = {
        "schema": "ownera.immunefi-discovery.v1",
        "source_mode": source_mode,
        "database": str(database_path.resolve()),
        "candidate_count": len(candidates),
        "candidates": [
            {
                "opportunity_id": str(item.opportunity_id),
                "evidence_id": str(item.evidence_id),
                "project": item.project,
                "slug": item.slug,
                "source_url": item.source_url,
                "max_bounty_ceiling": (
                    str(item.max_bounty_ceiling)
                    if item.max_bounty_ceiling is not None else None
                ),
                "currency_hint": "USD",
                "captured_at": item.captured_at.isoformat(),
                "status": "PENDING_OWNER_REVIEW",
            }
            for item in candidates
        ],
        "limitations": [
            "Maximum bounty is a ceiling, not expected or guaranteed revenue.",
            "Listings are untrusted until owner review and eligibility verification.",
            "No target scanning, report submission, external commitment, or payment occurs.",
        ],
    }
    if args.format == "json":
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"Immunefi discovery: {report['candidate_count']} active candidates")
        print(f"Database: {report['database']}")
        for item in report["candidates"]:
            ceiling = item["max_bounty_ceiling"] or "not listed"
            print(f"- {item['project']} | ceiling={ceiling} | {item['source_url']}")
        print("All candidates remain PENDING_OWNER_REVIEW; no external action was taken.")
    return 0


def _discover_openradar(args: argparse.Namespace) -> int:
    database_path = Path(args.database)
    database_path.parent.mkdir(parents=True, exist_ok=True)
    registry = SQLiteOpportunityEvidenceRegistry(
        database_path, authenticator=_NoOwnerAuthentication()
    )
    adapter = OpenRadarPublicFeedAdapter(registry)
    candidates = adapter.discover(limit=args.limit)
    sorted_candidates = sorted(
        candidates,
        key=lambda item: (
            item.relevance_score,
            item.published_at,
            item.feed_score if item.feed_score is not None else -1,
        ),
        reverse=True,
    )
    report = {
        "schema": "ownera.openradar-discovery.v1",
        "source_mode": "public_guest_feed",
        "database": str(database_path.resolve()),
        "feed_delay_hours": adapter.FEED_DELAY_HOURS,
        "contacts_available": False,
        "source_status_default": "UNKNOWN",
        "note": "OBSERVED means present in delayed feed, not verified open on the original platform. Feed score and OWNERA relevance score are not expected income or win probability.",
        "candidate_count": len(sorted_candidates),
        "candidates": [item.to_dict() for item in sorted_candidates],
    }
    if args.format == "json":
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(
            f"OpenRadar guest feed: {len(sorted_candidates)} gigs; "
            f"feed delay={adapter.FEED_DELAY_HOURS}h; contacts hidden"
        )
        for item in sorted_candidates[:30]:
            budget = (
                f"{item.budget} {item.currency or ''}".strip()
                if item.budget is not None else "budget unknown"
            )
            print(
                f"- [{item.relevance_score}/100] {item.title} | "
                f"{budget} | {item.published_at.isoformat()} | "
                f"{item.buyer_intent} | STATUS UNKNOWN | {item.source_url}"
            )
        print("All feed records are OBSERVED/PENDING evidence; verify original status before action.")
    return 0


def _rank_immunefi(args: argparse.Namespace) -> int:
    results = rank_immunefi(args.database, limit=args.limit)
    report = {
        "schema": "ownera.immunefi-triage.v1",
        "database": str(Path(args.database).resolve()),
        "result_count": len(results),
        "scoring_notice": "Research-fit triage only. Not exploit probability, eligibility, expected payout, or a promise of revenue.",
        "results": [item.to_dict() for item in results],
    }
    if args.format == "json":
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"Immunefi research shortlist: {len(results)}")
        for item in results:
            print(f"- [{item.tier} {item.score}/100] {item.project} | {item.source_url}")
            for reason in item.reasons:
                print(f"    + {reason}")
            for blocker in item.blockers:
                print(f"    BLOCKER: {blocker}")
            for check in item.manual_checks:
                print(f"    CHECK: {check}")
        print("Scores are triage signals only; verify official terms before any testing.")
    return 0


def _paid_work(args: argparse.Namespace) -> int:
    if args.paid_work_command == "sync-near-assignments":
        report = sync_assignments(args.database)
        print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
        return 0
    if args.paid_work_command == "retry-near-deliveries":
        from ownera.near_market_lifecycle import retry_pending_deliveries
        report = retry_pending_deliveries(args.database)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 1 if report["failures"] else 0
    pipeline = PaidWorkPipeline(args.database)
    if args.paid_work_command == "sync-near-market":
        report = sync_paid_work(args.database)
        print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
        return 0
    if args.paid_work_command == "ingest":
        payload = json.loads(Path(args.payload_file).read_text(encoding="utf-8"))
        opportunity, created = pipeline.ingest(payload)
        print(json.dumps({
            "schema": "ownera.paid-work-opportunity.v1",
            "created": created,
            "opportunity_id": str(opportunity.opportunity_id),
            "title": opportunity.title,
            "source_url": opportunity.source_url,
            "budget_min": str(opportunity.budget_min),
            "budget_max": str(opportunity.budget_max),
            "currency": opportunity.currency,
            "status": opportunity.status.value,
            "note": "Intake only. No proposal was sent and no customer was contacted.",
        }, ensure_ascii=False, indent=2))
        return 0
    if args.paid_work_command == "list":
        rows = [{
            "opportunity_id": str(item.opportunity_id),
            "title": item.title,
            "source_name": item.source_name,
            "source_url": item.source_url,
            "budget_min": str(item.budget_min),
            "budget_max": str(item.budget_max),
            "currency": item.currency,
            "capabilities": sorted(item.required_capabilities),
            "status": item.status.value,
        } for item in pipeline.opportunities]
        print(json.dumps({"schema": "ownera.paid-work-list.v1", "count": len(rows), "opportunities": rows}, ensure_ascii=False, indent=2))
        return 0
    if args.paid_work_command == "assess":
        from decimal import Decimal
        from uuid import UUID
        result = pipeline.assess(
            UUID(args.opportunity_id),
            delivery_cost=Decimal(args.delivery_cost),
            platform_fee_rate=Decimal(args.platform_fee_rate),
            contingency_rate=Decimal(args.contingency_rate),
            win_probability=Decimal(args.win_probability),
            minimum_net_margin=Decimal(args.minimum_net_margin),
            terms_reviewed=args.terms_reviewed,
            eligibility_confirmed=args.eligibility_confirmed,
        )
        print(json.dumps({
            "schema": "ownera.paid-work-assessment.v1",
            "opportunity_id": str(result.opportunity_id),
            "status": result.status.value,
            "conservative_revenue": str(result.conservative_revenue),
            "estimated_total_cost": str(result.estimated_total_cost),
            "estimated_net_profit": str(result.expected_net_profit),
            "estimated_net_margin": str(result.expected_net_margin),
            "risk_adjusted_value": str(result.risk_adjusted_value),
            "reasons": list(result.reasons),
            "notice": "Estimates only. Win probability is a manual assumption, not a model prediction or income forecast.",
        }, ensure_ascii=False, indent=2))
        return 0
    if args.paid_work_command == "draft":
        payload = json.loads(Path(args.payload_file).read_text(encoding="utf-8"))
        proposal = pipeline.draft_proposal(payload)
        print(json.dumps({
            "schema": "ownera.paid-work-proposal.v1",
            "proposal_id": str(proposal.proposal_id),
            "opportunity_id": str(proposal.opportunity_id),
            "status": proposal.status.value,
            "quote_amount": str(proposal.quote_amount),
            "currency": proposal.currency,
            "scope": proposal.scope,
            "acceptance_criteria": list(proposal.acceptance_criteria),
            "delivery_plan": list(proposal.delivery_plan),
            "note": "Draft only. Owner approval and manual submission are still required.",
        }, ensure_ascii=False, indent=2))
        return 0
    raise ValueError("unknown paid-work command")


def _qualify_paid_work(args: argparse.Namespace) -> int:
    payload = json.loads(Path(args.input_file).read_text(encoding="utf-8"))
    assessment = LocalOllamaRevenueScout(
        base_url=args.base_url, model=args.model, timeout_seconds=args.timeout
    ).qualify(payload)
    print(json.dumps(assessment.to_dict(), ensure_ascii=False, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ownera",
        description="OWNERA safe read-only discovery and operations CLI",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    discover = commands.add_parser(
        "discover-immunefi",
        help="discover public Immunefi listings and persist evidence",
    )
    default_db = os.environ.get("OWNERA_DB_PATH", "/var/lib/ownera/ownera.sqlite3")
    discover.add_argument("--database", default=default_db)
    discover.add_argument("--payload-file", help="use a saved JSON catalog instead of HTTP")
    discover.add_argument("--format", choices=("text", "json"), default="text")
    discover.set_defaults(handler=_discover_immunefi)

    openradar = commands.add_parser(
        "discover-openradar",
        help="capture public OpenRadar gig feed as OBSERVED evidence (not verified open)",
    )
    openradar.add_argument("--database", default=default_db)
    openradar.add_argument("--limit", type=int, default=100)
    openradar.add_argument("--format", choices=("text", "json"), default="text")
    openradar.set_defaults(handler=_discover_openradar)

    rank = commands.add_parser(
        "rank-immunefi",
        help="rank captured Immunefi evidence for manual research triage",
    )
    rank.add_argument("--database", default=default_db)
    rank.add_argument("--limit", type=int, default=10)
    rank.add_argument("--format", choices=("text", "json"), default="text")
    rank.set_defaults(handler=_rank_immunefi)

    scout = commands.add_parser(
        "scout", help="qualify a sourced paid-work candidate with the local Ollama model"
    )
    scout_commands = scout.add_subparsers(dest="scout_command", required=True)
    qualify = scout_commands.add_parser(
        "qualify", help="classify one candidate; no scraping, bidding, or customer contact"
    )
    qualify.add_argument("--input-file", required=True)
    qualify.add_argument("--base-url", default=os.environ.get("OWNERA_OLLAMA_URL", "http://127.0.0.1:11434"))
    qualify.add_argument("--model", default=os.environ.get("OWNERA_SCOUT_MODEL", "qwen2.5:0.5b"))
    qualify.add_argument("--timeout", type=float, default=180)
    qualify.set_defaults(handler=_qualify_paid_work)

    paid = commands.add_parser("paid-work", help="manage the manual-first paid-work pipeline")
    paid_commands = paid.add_subparsers(dest="paid_work_command", required=True)
    near = paid_commands.add_parser("sync-near-market", help="read open NEAR Agent Market jobs into Paid Work")
    near.add_argument("--database", default=default_db)
    near.set_defaults(handler=_paid_work)
    assignments = paid_commands.add_parser("sync-near-assignments", help="poll and persist direct-hire assignments")
    assignments.add_argument("--database", default=default_db)
    assignments.set_defaults(handler=_paid_work)
    delivery_retry = paid_commands.add_parser("retry-near-deliveries", help="resume prepared marketplace deliveries without rerunning workers")
    delivery_retry.add_argument("--database", default=default_db)
    delivery_retry.set_defaults(handler=_paid_work)
    ingest = paid_commands.add_parser("ingest", help="persist a manually sourced paid-work listing")
    ingest.add_argument("--database", default=default_db)
    ingest.add_argument("--payload-file", required=True)
    ingest.set_defaults(handler=_paid_work)
    listing = paid_commands.add_parser("list", help="list persisted paid-work opportunities")
    listing.add_argument("--database", default=default_db)
    listing.set_defaults(handler=_paid_work)
    assess = paid_commands.add_parser("assess", help="calculate conservative economics for an opportunity")
    assess.add_argument("--database", default=default_db)
    assess.add_argument("--opportunity-id", required=True)
    assess.add_argument("--delivery-cost", required=True)
    assess.add_argument("--platform-fee-rate", required=True)
    assess.add_argument("--contingency-rate", required=True)
    assess.add_argument("--win-probability", required=True)
    assess.add_argument("--minimum-net-margin", required=True)
    assess.add_argument("--terms-reviewed", action="store_true")
    assess.add_argument("--eligibility-confirmed", action="store_true")
    assess.set_defaults(handler=_paid_work)
    draft = paid_commands.add_parser("draft", help="create a proposal draft for a qualified opportunity")
    draft.add_argument("--database", default=default_db)
    draft.add_argument("--payload-file", required=True)
    draft.set_defaults(handler=_paid_work)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.handler(args)
    except (OSError, RuntimeError, ValueError, sqlite3.Error) as exc:
        print(f"ownera: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
