"""Authenticated NEAR Agent Market start/submit lifecycle adapter.

Contract source: https://market.near.ai/openapi.json and
https://market.near.ai/skill/flows/worker-lifecycle.md
"""
from __future__ import annotations

import json
import os
from collections.abc import Callable
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from ownera.near_market import API_BASE, NearMarketError

MAX_DELIVERABLE_BYTES = 256 * 1024


@dataclass(frozen=True)
class MarketplaceSubmission:
    assignment_id: str
    status: str
    submitted_at: str | None
    deliverable_hash: str | None


class NearMarketLifecycle:
    """REST adapter for worker-owned assignments; writes only start and submit."""

    def __init__(self, token: str | None = None, *, opener: Callable = urlopen, timeout: int = 30):
        self.token = token or os.environ.get("NEAR_AGENT_MARKET_API_TOKEN", "")
        if not self.token.strip():
            raise NearMarketError("NEAR_AGENT_MARKET_API_TOKEN is not configured")
        self.opener = opener
        self.timeout = timeout

    def _request(self, path: str, *, body: dict | None = None) -> dict:
        data = None if body is None else json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/json",
            "User-Agent": "OWNERA-PaidWork/0.2",
        }
        if data is not None:
            headers["Content-Type"] = "application/json"
        request = Request(API_BASE + path, data=data, headers=headers, method="POST")
        try:
            with self.opener(request, timeout=self.timeout) as response:
                raw = response.read()
            payload = json.loads(raw.decode("utf-8"))
        except HTTPError as exc:
            detail = exc.read(2000).decode("utf-8", errors="replace")
            raise NearMarketError(f"NEAR Agent Market returned HTTP {exc.code}: {detail}") from exc
        except (URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise NearMarketError(f"NEAR Agent Market request failed: {exc}") from exc
        if not isinstance(payload, dict):
            raise NearMarketError("NEAR Agent Market returned a non-object response")
        return payload

    def start_assignment(self, assignment_id: str) -> str:
        if not assignment_id or "/" in assignment_id:
            raise ValueError("assignment_id must be a non-empty path-safe id")
        payload = self._request(f"/v1/assignments/{assignment_id}/start")
        started_at = payload.get("startedAt")
        if not isinstance(started_at, str) or not started_at:
            raise NearMarketError("start response is missing startedAt")
        return started_at

    def submit_deliverable(self, assignment_id: str, markdown: str, *, files: tuple[str, ...] = ()) -> MarketplaceSubmission:
        if not assignment_id or "/" in assignment_id:
            raise ValueError("assignment_id must be a non-empty path-safe id")
        if not isinstance(markdown, str):
            raise TypeError("deliverable markdown must be text")
        size = len(markdown.encode("utf-8"))
        if not 1 <= size <= MAX_DELIVERABLE_BYTES:
            raise ValueError("deliverableMarkdown must be between 1 byte and 256 KiB")
        if len(files) > 5 or any(not isinstance(item, str) or not item.strip() for item in files):
            raise ValueError("files must contain at most five non-empty file references")
        payload = self._request(
            f"/v1/assignments/{assignment_id}/submit",
            body={"deliverableMarkdown": markdown, **({"files": list(files)} if files else {})},
        )
        if payload.get("assignmentId") != assignment_id or payload.get("status") != "submitted":
            raise NearMarketError("submit response does not confirm this assignment as submitted")
        return MarketplaceSubmission(
            assignment_id=assignment_id,
            status="submitted",
            submitted_at=payload.get("submittedAt"),
            deliverable_hash=payload.get("deliverableHash"),
        )


def _compose_text_deliverable(summary: str, records, registry) -> str:
    """Build a buyer-readable Markdown result from verified text artifacts.

    Binary artifacts need the separately documented marketplace file-upload
    flow; they are rejected rather than represented by unusable local hashes.
    """
    from pathlib import PurePosixPath

    sections = [f"# Delivery\n\n{summary.strip()}"]
    for record in records:
        content = registry.get(record.sha256)
        if b"\x00" in content:
            raise NearMarketError(f"binary artifact requires marketplace file upload: {record.artifact_name}")
        try:
            decoded = content.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise NearMarketError(f"non-UTF-8 artifact requires marketplace file upload: {record.artifact_name}") from exc
        fence = "```"
        while fence in decoded:
            fence += "`"
        name = PurePosixPath(record.artifact_name.replace("__", "/")).name
        sections.append(f"## Artifact: {name}\n\nSHA-256: `{record.sha256}`\n\n{fence}text\n{decoded.rstrip()}\n{fence}")
    markdown = "\n\n".join(sections).strip() + "\n"
    if len(markdown.encode("utf-8")) > MAX_DELIVERABLE_BYTES:
        raise NearMarketError("text artifacts exceed marketplace Markdown limit; use marketplace file upload")
    return markdown


def execute_and_deliver_assignment(
    assignment_item: dict,
    spec,
    *,
    database_path,
    worker,
    runtime,
    lifecycle: NearMarketLifecycle,
):
    """Start a real in-progress assignment, run its trusted worker spec, submit it.

    The assignment/job brief is untrusted input and is never converted to a
    command. `spec` must come from OWNERA's trusted planner/policy layer.
    """
    from ownera.artifact_registry import SQLiteArtifactRegistry
    from ownera.near_market_dispatch import dispatch_started_assignment

    assignment = assignment_item.get("assignment")
    job = assignment_item.get("job")
    if not isinstance(assignment, dict) or not isinstance(job, dict):
        raise NearMarketError("assignment item must contain assignment and job objects")
    assignment_id = assignment.get("assignmentId")
    job_id = assignment.get("jobId")
    if not isinstance(assignment_id, str) or not assignment_id or not isinstance(job_id, str) or not job_id:
        raise NearMarketError("assignment item is missing assignmentId or jobId")
    if assignment.get("status") != "in_progress":
        raise NearMarketError("only in_progress marketplace assignments can be executed")
    if spec.assignment_id != assignment_id or spec.job_id != job_id:
        raise NearMarketError("trusted execution spec does not match marketplace assignment")
    if assignment.get("startedAt") is None:
        lifecycle.start_assignment(assignment_id)

    local_submission = dispatch_started_assignment(
        spec, database_path=database_path, worker=worker, runtime=runtime
    )
    registry = SQLiteArtifactRegistry(database_path)
    markdown = _compose_text_deliverable(
        spec.summary, local_submission.artifact_records, registry
    )
    remote_submission = lifecycle.submit_deliverable(assignment_id, markdown)
    return local_submission, remote_submission
