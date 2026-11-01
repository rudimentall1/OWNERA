"""Policy-bounded bidding on public NEAR Agent Market standard jobs.

The module fails closed: no bid is sent unless the owner explicitly enables
bidding and every deterministic policy check passes. Buyer text is data only.
"""
from __future__ import annotations

import json
import os
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from ownera.near_market import API_BASE, NearMarketError, _capabilities


@dataclass(frozen=True)
class BidPolicy:
    enabled: bool = False
    min_amount: Decimal = Decimal("5")
    max_amount: Decimal = Decimal("25")
    max_age_days: int = 30
    max_acceptance_window_days: int = 7
    max_pending_bids: int = 20
    max_active_assignments: int = 1
    max_total_commitments: int = 20
    max_submissions_per_run: int = 5
    allowed_capabilities: frozenset[str] = frozenset({
        "python", "javascript", "api_integration", "automation",
        "data_processing", "research", "security_review",
    })
    blocked_terms: tuple[str, ...] = (
        "book a", "booking", "reservation", "flight", "hotel", "travel",
        "restaurant", "uber eats", "order a", "purchase", "buy on behalf",
        "place an order", "phone call", "call-for-me", "make a call",
        "credit card", "bank transfer", "withdraw", "send money", "invest",
        "trading", "medical advice", "legal advice", "sign a contract",
        "deploy and host", "ongoing hosting", "24/7 hosting",
    )

    @classmethod
    def from_env(cls) -> BidPolicy:
        def dec(name: str, default: str) -> Decimal:
            try:
                value = Decimal(os.environ.get(name, default))
            except InvalidOperation as exc:
                raise ValueError(f"{name} must be a decimal") from exc
            if not value.is_finite():
                raise ValueError(f"{name} must be finite")
            return value

        return cls(
            enabled=os.environ.get("OWNERA_NEAR_BIDDING_ENABLED", "false").casefold() == "true",
            min_amount=dec("OWNERA_NEAR_BID_MIN_USDC", "5"),
            max_amount=dec("OWNERA_NEAR_BID_MAX_USDC", "25"),
            max_age_days=int(os.environ.get("OWNERA_NEAR_BID_MAX_AGE_DAYS", "30")),
            max_acceptance_window_days=int(os.environ.get("OWNERA_NEAR_BID_MAX_ACCEPTANCE_DAYS", "7")),
            max_pending_bids=int(os.environ.get("OWNERA_NEAR_BID_MAX_PENDING", "20")),
            max_active_assignments=int(os.environ.get("OWNERA_NEAR_BID_MAX_ACTIVE", "1")),
            max_total_commitments=int(os.environ.get("OWNERA_NEAR_BID_MAX_TOTAL_COMMITMENTS", "20")),
            max_submissions_per_run=int(os.environ.get("OWNERA_NEAR_BID_MAX_PER_RUN", "5")),
        )

    def __post_init__(self) -> None:
        if self.min_amount <= 0 or self.max_amount < self.min_amount:
            raise ValueError("invalid USDC bid range")
        if min(self.max_age_days, self.max_acceptance_window_days, self.max_pending_bids, self.max_active_assignments, self.max_total_commitments, self.max_submissions_per_run) < 1:
            raise ValueError("bid policy limits must be positive")


def _request_json(method: str, path: str, token: str, payload: dict | None = None) -> dict:
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "User-Agent": "OWNERA-PaidWork/0.2",
    }
    if body is not None:
        headers["Content-Type"] = "application/json"
    request = Request(API_BASE + path, data=body, headers=headers, method=method)
    try:
        with urlopen(request, timeout=25) as response:
            result = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        detail = exc.read(1000).decode("utf-8", errors="replace")
        raise NearMarketError(f"NEAR Agent Market returned HTTP {exc.code}: {detail}") from exc
    except (URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise NearMarketError(f"NEAR Agent Market request failed: {exc}") from exc
    if not isinstance(result, dict):
        raise NearMarketError("marketplace response must be a JSON object")
    return result


def fetch_bid_context(token: str | None = None) -> tuple[list[dict], list[dict], list[dict]]:
    credential = token or os.environ.get("NEAR_AGENT_MARKET_API_TOKEN", "")
    if not credential.strip():
        raise NearMarketError("NEAR_AGENT_MARKET_API_TOKEN is not configured")
    board = _request_json("GET", "/v1/jobs/board?kind=standard&sort=recent&limit=100", credential)
    bids = _request_json("GET", "/v1/agents/me/bids?status=all&limit=100", credential)
    assignments = _request_json("GET", "/v1/agents/me/assignments?status=all&limit=100", credential)
    if not isinstance(board.get("jobs"), list) or not isinstance(bids.get("bids"), list) or not isinstance(assignments.get("assignments"), list):
        raise NearMarketError("unexpected marketplace response shape")
    return board["jobs"], bids["bids"], assignments["assignments"]


def qualify_job(job: dict, policy: BidPolicy, *, now: datetime | None = None) -> tuple[bool, tuple[str, ...]]:
    reasons: list[str] = []
    if not isinstance(job.get("jobId"), str) or not job["jobId"].strip():
        reasons.append("missing_job_id")
    if str(job.get("status", "")).casefold() not in {"open", "filling"}:
        reasons.append("job_not_open")
    if job.get("jobKind", "standard") != "standard":
        reasons.append("not_standard_job")
    if job.get("isPrivate", False):
        reasons.append("private_job")
    try:
        if int(job.get("currentMaxSlots", 1)) < 1:
            reasons.append("no_slots_available")
    except (TypeError, ValueError):
        reasons.append("invalid_slot_count")
    if job.get("budgetToken") != "USDC":
        reasons.append("unsupported_payment_rail")
    try:
        amount = Decimal(str(job.get("budgetAmount")))
        if not amount.is_finite() or amount < policy.min_amount or amount > policy.max_amount:
            reasons.append("budget_outside_policy")
    except (InvalidOperation, ValueError, TypeError):
        reasons.append("missing_or_invalid_budget")
    if job.get("minBuilderVerification", "none") != "none":
        reasons.append("builder_verification_required")
    if job.get("requiresVerifiable", False):
        reasons.append("verifiable_delivery_required")
    try:
        acceptance_days = int(job.get("acceptanceWindowDays"))
        if acceptance_days < 1 or acceptance_days > policy.max_acceptance_window_days:
            reasons.append("acceptance_window_outside_policy")
    except (TypeError, ValueError):
        reasons.append("missing_or_invalid_acceptance_window")
    created = job.get("createdAt")
    try:
        created_at = datetime.fromisoformat(str(created))
        current = now or datetime.now(timezone.utc)
        if created_at.tzinfo is None or created_at > current + timedelta(minutes=5):
            reasons.append("invalid_created_at")
        elif current - created_at > timedelta(days=policy.max_age_days):
            reasons.append("listing_too_old")
    except (TypeError, ValueError):
        reasons.append("missing_or_invalid_created_at")
    capabilities = set(_capabilities(job))
    if not capabilities.intersection(policy.allowed_capabilities):
        reasons.append("no_capability_match")
    text = f"{job.get('title', '')} {job.get('description', '')}".casefold()
    if any(term in text for term in policy.blocked_terms):
        reasons.append("external_side_effect_or_restricted_scope")
    return not reasons, tuple(reasons)


def generate_proposal(job: dict, amount: Decimal) -> str:
    """Build a truthful, task-shaped proposal without a slow model dependency."""
    title = str(job.get("title", "the requested task")).strip()
    description = str(job.get("description", "")).casefold()
    tags = {str(tag).casefold() for tag in job.get("tags", []) if isinstance(tag, str)}
    title_key = title.casefold()
    scoped = {
        "completed jobs per day": "Define completed-job events and exclusions, build the marketplace funnel with formulas, growth accounting, a one-page dashboard and weekly leading indicators. First sources: NEAR Agent Market API/docs, Stripe platform docs, and published marketplace metrics from Airbnb, Etsy and Upwork.",
        "distribution channels": "Compare listing requirements, review, adoption evidence, cost and eligibility across the official MCP Registry, Smithery, Glama, PulseMCP, mcp.so, Claude connectors, ChatGPT apps, A2A/x402 catalogs, GitHub, Hugging Face, npm and PyPI. Rank channels and give exact submission steps for the top five. First sources: official directory submission docs and OpenAI/Anthropic platform policies.",
        "specialist": "Compare delegation and integration paths across OpenAI Agents SDK, Claude Agent SDK, LangGraph, CrewAI, AutoGen, Google ADK, Vercel AI SDK and n8n. Deliver a comparison and three concrete integration specs covering installation, tool schema, auth/payment and asynchronous results. First sources: each framework's official documentation.",
        "outsource repeatedly": "Survey recurring outsourced task families and rank 15–20 by demand evidence, unit price, latency, output verifiability and fit for agent-to-agent delivery. Separate measured facts from estimates. First sources: official pricing pages for scraping, OCR, transcription, translation and model APIs, plus public GitHub, Reddit and framework-community discussions.",
        "agent-to-agent commerce": "Compare x402, Virtuals ACP, Olas, Fetch.ai Agentverse, Google A2A and agent marketplaces by traded service, buyer type, verifiable volume, price, discovery, payment and fees. Mark self-reported metrics. First sources: Coinbase x402, Virtuals, Olas, Fetch.ai and Google A2A primary documentation, then public marketplace/API data.",
        "sagekai": "Search the public NEAR Agent Market agent directory and public agent profiles for the exact name SageKai; verify a matching handle and profile URL, distinguish similar names, and report not found if there is no verifiable public match. First sources: the public Agent Market agent directory and agent-search API.",
    }
    for key, details in scoped.items():
        if key in title_key:
            proposal = f"Bid: {amount} USDC. {details} I will cite URLs actually opened, label estimates, and state evidence gaps rather than guess."
            if len(proposal) > 4000:
                raise NearMarketError("generated proposal exceeds marketplace limit")
            return proposal
    research = "research" in tags or any(word in title.casefold() for word in ("research", "analysis", "economics", "benchmark"))
    if research:
        if "micro-job" in title.casefold() or "payment" in description or "judge" in description:
            method = (
                "I will produce a 1,000–2,500-word English Markdown report with a transparent cost model, "
                "calculations at each requested price point, a break-even estimate, and ranked recommendations. "
                "I will separate published prices from assumptions and cite primary sources. I will start with "
                "NEAR Agent Market terms, Stripe pricing, RapidAPI provider fees, Upwork and Fiverr fees, "
                "Twilio pricing, Modal and Replicate compute rates, OpenRouter pricing, and Coinbase x402 docs."
            )
        else:
            method = (
                f"I will review the full brief and relevant primary sources for {title}, then deliver a "
                "structured Markdown report with cited evidence, explicit assumptions, and actionable findings. "
                "I will distinguish verified facts from estimates and identify any evidence gaps rather than guess."
            )
    elif "python" in tags or "javascript" in tags or "api" in title.casefold():
        method = (
            f"I will implement the scoped requirements for {title}, keep changes limited to the agreed surface, "
            "add tests for the main success and failure paths, and provide the changed files plus reproducible "
            "verification results. I will flag missing requirements before making assumptions."
        )
    else:
        method = (
            f"I will map the supplied requirements for {title} into a bounded delivery plan, complete the "
            "requested output, and provide the result with a concise verification note and supporting evidence. "
            "I will not claim unverified results or perform unrelated external actions."
        )
    proposal = f"Bid: {amount} USDC. {method}"
    if len(proposal) > 4000:
        raise NearMarketError("generated proposal exceeds marketplace limit")
    return proposal


def run_bid_cycle(
    database_path: str | Path,
    *,
    policy: BidPolicy | None = None,
    token: str | None = None,
    dry_run: bool = True,
    jobs: list[dict] | None = None,
    bids: list[dict] | None = None,
    assignments: list[dict] | None = None,
    proposal_factory=generate_proposal,
) -> dict:
    rules = policy or BidPolicy.from_env()
    if not dry_run and not rules.enabled:
        raise PermissionError("autonomous bidding is disabled; set OWNERA_NEAR_BIDDING_ENABLED=true")
    credential = token or os.environ.get("NEAR_AGENT_MARKET_API_TOKEN", "")
    if jobs is None or bids is None or assignments is None:
        live_jobs, live_bids, live_assignments = fetch_bid_context(credential)
        jobs = live_jobs if jobs is None else jobs
        bids = live_bids if bids is None else bids
        assignments = live_assignments if assignments is None else assignments
    known_jobs = {str(row.get("jobId")) for row in bids}
    pending = sum(1 for row in bids if str(row.get("status", "")).casefold() == "pending")
    active = sum(
        1 for row in assignments
        if str((row.get("assignment") or row).get("status", "")).casefold() in {"in_progress", "submitted", "disputed"}
    )
    output = {"schema": "ownera.near-market-bid-cycle.v1", "mode": "dry_run" if dry_run else "live", "scanned": len(jobs), "eligible": [], "skipped": [], "submitted": [], "pending_before": pending, "active_before": active}
    if pending >= rules.max_pending_bids:
        output["skipped"].append({"reason": "pending_bid_limit_reached"})
        return output
    if active >= rules.max_active_assignments:
        output["skipped"].append({"reason": "active_assignment_limit_reached"})
        return output
    if pending + active >= rules.max_total_commitments:
        output["skipped"].append({"reason": "total_commitment_limit_reached"})
        return output
    for job in jobs:
        job_id = str(job.get("jobId", ""))
        if job_id in known_jobs:
            output["skipped"].append({"job_id": job_id, "reason": "already_bid"})
            continue
        eligible, reasons = qualify_job(job, rules)
        if not eligible:
            output["skipped"].append({"job_id": job_id, "reasons": list(reasons)})
            continue
        amount = Decimal(str(job["budgetAmount"]))
        item = {"job_id": job_id, "title": job.get("title", ""), "amount": str(amount), "currency": "USDC"}
        output["eligible"].append(item)
        if dry_run:
            continue
        proposal = proposal_factory(job, amount)
        payload = {"amount": str(amount), "proposal": proposal}
        response = _request_json("POST", f"/v1/jobs/{job_id}/bids", credential, payload)
        submitted = {**item, "bid_id": response.get("bidId"), "status": response.get("status", "pending")}
        output["submitted"].append(submitted)
        pending += 1
        if len(output["submitted"]) >= rules.max_submissions_per_run or pending >= rules.max_pending_bids:
            break
    if not dry_run:
        db = sqlite3.connect(str(database_path), timeout=10)
        try:
            db.execute("""CREATE TABLE IF NOT EXISTS near_market_bid_audit (
                bid_id TEXT PRIMARY KEY, job_id TEXT NOT NULL, amount TEXT NOT NULL,
                status TEXT NOT NULL, created_at TEXT NOT NULL
            )""")
            now = datetime.now(timezone.utc).isoformat()
            for row in output["submitted"]:
                if row.get("bid_id"):
                    db.execute("INSERT OR IGNORE INTO near_market_bid_audit VALUES (?, ?, ?, ?, ?)", (row["bid_id"], row["job_id"], row["amount"], row["status"], now))
            db.commit()
        finally:
            db.close()
    return output
