"""Idempotent intake for direct-hire NEAR Agent Market assignments."""
from __future__ import annotations

import json
import os
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from ownera.near_market import API_BASE, NearMarketError


@dataclass(frozen=True)
class AssignmentSyncReport:
    fetched: int
    created: int
    unchanged: int
    ignored: int
    plans_prepared: int = 0

    def to_dict(self) -> dict:
        return {
            "schema": "ownera.near-market-assignment-sync.v2",
            "fetched": self.fetched,
            "created": self.created,
            "unchanged": self.unchanged,
            "ignored": self.ignored,
            "plans_prepared": self.plans_prepared,
            "external_actions": "none",
        }


def fetch_assignments(token: str | None = None, *, opener=urlopen, page_size: int = 100, max_records: int = 10000) -> list[dict]:
    """Fetch every assignment status with bounded pagination.

    The default worker feed may omit completed assignments. `status=all` is
    required for reliable award and delivery reconciliation. Pagination follows
    the same documented query contract used by NearMarketLifecycle.
    """
    credential = token or os.environ.get("NEAR_AGENT_MARKET_API_TOKEN", "")
    if not credential.strip():
        raise NearMarketError("NEAR_AGENT_MARKET_API_TOKEN is not configured")
    if not 1 <= page_size <= 100 or not page_size <= max_records <= 10000:
        raise ValueError("page_size must be 1..100 and max_records page_size..10000")

    rows: list[dict] = []
    offset = 0
    while offset < max_records:
        query = urlencode({"status": "all", "limit": page_size, "offset": offset})
        request = Request(
            f"{API_BASE}/v1/agents/me/assignments?{query}",
            headers={"Authorization": f"Bearer {credential}", "Accept": "application/json", "User-Agent": "OWNERA-PaidWork/0.2"},
        )
        try:
            with opener(request, timeout=25) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            detail = exc.read(1000).decode("utf-8", errors="replace")
            raise NearMarketError(f"NEAR Agent Market returned HTTP {exc.code}: {detail}") from exc
        except (URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise NearMarketError(f"NEAR Agent Market request failed: {exc}") from exc
        if not isinstance(payload, dict) or not isinstance(payload.get("assignments"), list):
            raise NearMarketError("assignment response must contain an assignments list")
        page = payload["assignments"]
        if any(not isinstance(item, dict) for item in page):
            raise NearMarketError("assignment response contains a non-object record")
        rows.extend(page)
        if len(page) < page_size:
            break
        offset += len(page)
    if len(rows) >= max_records and len(rows) % page_size == 0:
        raise NearMarketError(f"assignment feed exceeded the {max_records}-record safety limit")
    return rows


def sync_assignments(database_path: str | Path, *, token: str | None = None, assignments: list[dict] | None = None) -> AssignmentSyncReport:
    rows = fetch_assignments(token) if assignments is None else assignments
    db = sqlite3.connect(str(database_path))
    created = unchanged = ignored = plans_prepared = 0
    try:
        db.execute("""CREATE TABLE IF NOT EXISTS near_market_assignments (
            assignment_id TEXT PRIMARY KEY,
            job_id TEXT NOT NULL,
            status TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            first_seen_at TEXT NOT NULL,
            last_seen_at TEXT NOT NULL
        )""")
        db.execute("""CREATE TABLE IF NOT EXISTS near_market_assignment_plans (
            assignment_id TEXT PRIMARY KEY,
            job_id TEXT NOT NULL,
            plan_sha256 TEXT NOT NULL,
            plan_json TEXT NOT NULL,
            state TEXT NOT NULL CHECK(state IN ('PLAN_READY_NOT_EXECUTABLE','NOT_ACTIVE')),
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )""")
        now = datetime.now(timezone.utc).isoformat()
        for item in rows:
            # The documented worker endpoint returns {assignment, job, latestMessage}.
            # Keep the complete source snapshot while normalizing index columns.
            assignment = item.get("assignment") if isinstance(item.get("assignment"), dict) else item
            job = item.get("job") if isinstance(item.get("job"), dict) else {}
            assignment_id = assignment.get("assignmentId")
            job_id = assignment.get("jobId") or job.get("jobId")
            status = assignment.get("status")
            if not isinstance(assignment_id, str) or not assignment_id.strip() or not isinstance(job_id, str) or not job_id.strip() or not isinstance(status, str) or not status.strip():
                ignored += 1
                continue
            encoded = json.dumps(item, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
            existing = db.execute("SELECT payload_json FROM near_market_assignments WHERE assignment_id=?", (assignment_id,)).fetchone()
            if existing is None:
                db.execute("INSERT INTO near_market_assignments VALUES (?, ?, ?, ?, ?, ?)", (assignment_id, job_id, status, encoded, now, now))
                created += 1
            else:
                if existing[0] == encoded:
                    unchanged += 1
                else:
                    db.execute("UPDATE near_market_assignments SET job_id=?, status=?, payload_json=?, last_seen_at=? WHERE assignment_id=?", (job_id, status, encoded, now, assignment_id))
                    created += 1

            # A deterministic plan is persisted for supported active research
            # jobs. It contains no executable command and causes no external action.
            from ownera.near_market_research_planner import build_assignment_plan
            plan = build_assignment_plan(item)
            if plan is not None:
                plan_json = json.dumps(plan, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
                cursor = db.execute(
                    """INSERT INTO near_market_assignment_plans
                       (assignment_id,job_id,plan_sha256,plan_json,state,created_at,updated_at)
                       VALUES(?,?,?,?,?,?,?)
                       ON CONFLICT(assignment_id) DO UPDATE SET
                         job_id=excluded.job_id,
                         plan_sha256=excluded.plan_sha256,
                         plan_json=excluded.plan_json,
                         state=excluded.state,
                         updated_at=excluded.updated_at
                       WHERE near_market_assignment_plans.plan_sha256 != excluded.plan_sha256
                          OR near_market_assignment_plans.state != excluded.state""",
                    (assignment_id, job_id, plan["plan_sha256"], plan_json, plan["execution_state"], now, now),
                )
                plans_prepared += max(0, cursor.rowcount)
            elif status.casefold() not in {"assigned", "accepted", "started", "in_progress"}:
                db.execute(
                    "UPDATE near_market_assignment_plans SET state='NOT_ACTIVE',updated_at=? WHERE assignment_id=? AND state='PLAN_READY_NOT_EXECUTABLE'",
                    (now, assignment_id),
                )
        db.commit()
    finally:
        db.close()
    return AssignmentSyncReport(len(rows), created, unchanged, ignored, plans_prepared)
