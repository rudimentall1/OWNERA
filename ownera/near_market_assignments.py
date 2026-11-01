"""Idempotent intake for direct-hire NEAR Agent Market assignments."""
from __future__ import annotations

import json
import os
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from ownera.near_market import API_BASE, NearMarketError


@dataclass(frozen=True)
class AssignmentSyncReport:
    fetched: int
    created: int
    unchanged: int
    ignored: int

    def to_dict(self) -> dict:
        return {
            "schema": "ownera.near-market-assignment-sync.v1",
            "fetched": self.fetched,
            "created": self.created,
            "unchanged": self.unchanged,
            "ignored": self.ignored,
            "external_actions": "none",
        }


def fetch_assignments(token: str | None = None) -> list[dict]:
    credential = token or os.environ.get("NEAR_AGENT_MARKET_API_TOKEN", "")
    if not credential.strip():
        raise NearMarketError("NEAR_AGENT_MARKET_API_TOKEN is not configured")
    request = Request(
        f"{API_BASE}/v1/agents/me/assignments",
        headers={"Authorization": f"Bearer {credential}", "Accept": "application/json", "User-Agent": "OWNERA-PaidWork/0.1"},
    )
    try:
        with urlopen(request, timeout=25) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        detail = exc.read(1000).decode("utf-8", errors="replace")
        raise NearMarketError(f"NEAR Agent Market returned HTTP {exc.code}: {detail}") from exc
    except (URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise NearMarketError(f"NEAR Agent Market request failed: {exc}") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("assignments"), list):
        raise NearMarketError("assignment response must contain an assignments list")
    if any(not isinstance(item, dict) for item in payload["assignments"]):
        raise NearMarketError("assignment response contains a non-object record")
    return payload["assignments"]


def sync_assignments(database_path: str | Path, *, token: str | None = None, assignments: list[dict] | None = None) -> AssignmentSyncReport:
    rows = fetch_assignments(token) if assignments is None else assignments
    db = sqlite3.connect(str(database_path))
    created = unchanged = ignored = 0
    try:
        db.execute("""CREATE TABLE IF NOT EXISTS near_market_assignments (
            assignment_id TEXT PRIMARY KEY,
            job_id TEXT NOT NULL,
            status TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            first_seen_at TEXT NOT NULL,
            last_seen_at TEXT NOT NULL
        )""")
        now = datetime.now(timezone.utc).isoformat()
        for item in rows:
            assignment_id = item.get("assignmentId")
            job_id = item.get("jobId")
            status = item.get("status")
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
        db.commit()
    finally:
        db.close()
    return AssignmentSyncReport(len(rows), created, unchanged, ignored)
