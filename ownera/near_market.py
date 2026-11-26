"""Read-only NEAR Agent Market discovery adapter for the Paid Work pipeline."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from uuid import NAMESPACE_URL, uuid5

from ownera.paid_work import PaidWorkError, PaidWorkPipeline

API_BASE = "https://market.near.ai"
SOURCE_NAME = "NEAR Agent Market"


class NearMarketError(RuntimeError):
    """Marketplace transport or response error."""


@dataclass(frozen=True)
class SyncReport:
    fetched: int
    created: int
    unchanged: int
    conflicts: tuple[str, ...]
    ignored: int

    def to_dict(self) -> dict:
        return {
            "schema": "ownera.near-market-sync.v1",
            "fetched": self.fetched,
            "created": self.created,
            "unchanged": self.unchanged,
            "conflicts": list(self.conflicts),
            "ignored": self.ignored,
            "external_actions": "none",
        }


def _request_json(path: str, token: str, *, timeout: int = 25) -> dict:
    request = Request(
        API_BASE + path,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "User-Agent": "OWNERA-PaidWork/0.1",
        },
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        detail = exc.read(1000).decode("utf-8", errors="replace")
        raise NearMarketError(f"NEAR Agent Market returned HTTP {exc.code}: {detail}") from exc
    except (URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise NearMarketError(f"NEAR Agent Market request failed: {exc}") from exc
    if not isinstance(payload, dict):
        raise NearMarketError("unexpected marketplace response shape")
    return payload


def fetch_jobs(token: str | None = None) -> list[dict]:
    credential = token or os.environ.get("NEAR_AGENT_MARKET_API_TOKEN", "")
    if not credential.strip():
        raise NearMarketError("NEAR_AGENT_MARKET_API_TOKEN is not configured")
    payload = _request_json("/v1/jobs/board?kind=standard", credential)
    jobs = payload.get("jobs")
    if not isinstance(jobs, list) or any(not isinstance(job, dict) for job in jobs):
        raise NearMarketError("marketplace response does not contain a valid jobs list")
    return jobs


def _capabilities(job: dict) -> list[str]:
    tags = {str(tag).casefold() for tag in job.get("tags", []) if isinstance(tag, str)}
    text = str(job.get("title", "")).casefold()
    mapping = {
        "python": {"python"},
        "javascript": {"javascript", "typescript", "node"},
        "smart_contracts": {"solidity", "evm", "smart contract", "web3"},
        "security_review": {"security", "audit", "vulnerability", "sentinel"},
        "api_integration": {"api", "mcp", "integration"},
        "research": {"research", "analysis", "benchmark", "economics"},
        "data_processing": {"data", "parser", "scraping"},
        "video_processing": {"video", "dubbing", "clipping", "media"},
        "automation": {"automation", "agent", "workflow"},
    }
    found = [
        cap for cap, needles in mapping.items() if any(n in tags or n in text for n in needles)
    ]
    return sorted(set(found)) or ["general_software"]


def sync_paid_work(
    database_path: str | Path, *, token: str | None = None, jobs: list[dict] | None = None
) -> SyncReport:
    rows = fetch_jobs(token) if jobs is None else jobs
    pipeline = PaidWorkPipeline(database_path)
    created = unchanged = ignored = 0
    conflicts: list[str] = []
    existing_by_id = {item.opportunity_id: item for item in pipeline.opportunities}
    for job in rows:
        job_id = job.get("jobId")
        status = str(job.get("status", "")).casefold()
        title_hint = str(job.get("title", "")).casefold()
        description_hint = str(job.get("description", "")).casefold()
        if (
            not job_id
            or status not in {"open", "filling"}
            or job.get("isPrivate")
            or "reject test" in title_hint
            or "reject test" in description_hint
        ):
            ignored += 1
            continue
        try:
            amount = Decimal(str(job.get("budgetAmount", "0")))
        except (InvalidOperation, ValueError):
            ignored += 1
            continue
        currency = str(job.get("budgetToken") or "USD").upper()
        if not amount.is_finite() or amount < 0 or len(currency) not in (3, 4):
            ignored += 1
            continue
        source_url = f"{API_BASE}/jobs/{job_id}"
        opportunity_id = uuid5(NAMESPACE_URL, f"ownera-near-market:{job_id}")
        description = str(job.get("description") or "No description supplied by marketplace.")
        title = str(job.get("title") or "Untitled marketplace job")
        existing = existing_by_id.get(opportunity_id)
        if existing is not None:
            comparable = (
                existing.title,
                existing.description,
                existing.budget_min,
                existing.budget_max,
                existing.currency,
            )
            incoming = (title, description, amount, amount, currency)
            if comparable == incoming:
                unchanged += 1
            else:
                conflicts.append(str(job_id))
            continue
        payload = {
            "opportunity_id": str(opportunity_id),
            "title": title,
            "description": description,
            "source_name": SOURCE_NAME,
            "source_url": source_url,
            "budget_min": str(amount),
            "budget_max": str(amount),
            "currency": currency,
            "required_capabilities": _capabilities(job),
            "evidence_refs": [source_url],
            "discovered_at": datetime.now(timezone.utc).isoformat(),
        }
        try:
            _, was_created = pipeline.ingest(payload)
            created += int(was_created)
            unchanged += int(not was_created)
        except (PaidWorkError, ValueError):
            conflicts.append(str(job_id))
    return SyncReport(len(rows), created, unchanged, tuple(conflicts), ignored)
