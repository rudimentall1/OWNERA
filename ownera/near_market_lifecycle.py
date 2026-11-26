"""Authenticated NEAR Agent Market start/submit lifecycle adapter.

Contract source: https://market.near.ai/openapi.json and
https://market.near.ai/skill/flows/worker-lifecycle.md
"""
from __future__ import annotations

import hashlib
import json
import mimetypes
import os
from collections.abc import Callable
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from ownera.near_market import API_BASE, NearMarketError

MAX_DELIVERABLE_BYTES = 256 * 1024
MAX_MARKETPLACE_FILE_BYTES = 100 * 1024 * 1024
MAX_MARKETPLACE_FILES = 5


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

    def _request(self, path: str, *, body: dict | None = None, method: str = "POST") -> dict:
        data = None if body is None else json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/json",
            "User-Agent": "OWNERA-PaidWork/0.2",
        }
        if data is not None:
            headers["Content-Type"] = "application/json"
        request = Request(API_BASE + path, data=data, headers=headers, method=method)
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

    def get_assignment_status(self, assignment_id: str) -> str:
        """Read the assignment from the authenticated all-statuses worker feed."""
        if not assignment_id or "/" in assignment_id:
            raise ValueError("assignment_id must be a non-empty path-safe id")
        from urllib.parse import urlencode
        offset = 0
        while offset < 10000:
            query = urlencode({"status": "all", "limit": 100, "offset": offset})
            payload = self._request(f"/v1/agents/me/assignments?{query}", method="GET")
            rows = payload.get("assignments")
            if not isinstance(rows, list):
                raise NearMarketError("assignment status response is missing assignments")
            for item in rows:
                assignment = item.get("assignment") if isinstance(item, dict) else None
                if isinstance(assignment, dict) and assignment.get("assignmentId") == assignment_id:
                    status = assignment.get("status")
                    if isinstance(status, str) and status:
                        return status
                    raise NearMarketError("assignment status response has no status")
            if len(rows) < 100:
                break
            offset += len(rows)
        raise NearMarketError("assignment was not found in the authenticated assignment feed")

    def start_assignment(self, assignment_id: str) -> str:
        if not assignment_id or "/" in assignment_id:
            raise ValueError("assignment_id must be a non-empty path-safe id")
        payload = self._request(f"/v1/assignments/{assignment_id}/start")
        started_at = payload.get("startedAt")
        if not isinstance(started_at, str) or not started_at:
            raise NearMarketError("start response is missing startedAt")
        return started_at

    def upload_file(self, filename: str, content: bytes, *, content_type: str | None = None) -> str:
        """Reserve, PUT and complete one marketplace-owned file; return its fileId."""
        if not isinstance(filename, str) or not filename or len(filename) > 255 or any(ord(c) < 32 for c in filename) or "/" in filename or "\\" in filename:
            raise ValueError("filename must be a plain filename of at most 255 characters")
        if not isinstance(content, bytes) or not 1 <= len(content) <= MAX_MARKETPLACE_FILE_BYTES:
            raise ValueError("file content must be between 1 byte and 100 MiB")
        mime = content_type or mimetypes.guess_type(filename)[0] or "application/octet-stream"
        reserved = self._request("/v1/files", body={"filename": filename, "byteSize": len(content)})
        file_id = reserved.get("fileId")
        direct_url = reserved.get("directUploadUrl")
        if not isinstance(file_id, str) or not file_id or not isinstance(direct_url, str):
            raise NearMarketError("file reservation response is missing fileId or directUploadUrl")
        parsed = urlparse(direct_url)
        if parsed.scheme != "https" or not parsed.netloc:
            raise NearMarketError("marketplace returned an unsafe direct upload URL")
        upload_request = Request(direct_url, data=content, headers={"Content-Type": mime}, method="PUT")
        try:
            with self.opener(upload_request, timeout=self.timeout) as response:
                response.read(1024)
        except (HTTPError, URLError, TimeoutError) as exc:
            # Do not print the presigned URL: it is a temporary bearer capability.
            raise NearMarketError(f"marketplace object upload failed: {type(exc).__name__}") from exc
        completed = self._request(f"/v1/files/{file_id}/complete")
        expected_hash = hashlib.sha256(content).hexdigest()
        if completed.get("fileId") != file_id or completed.get("byteSize") != len(content) or completed.get("sha256") != expected_hash:
            raise NearMarketError("completed marketplace file metadata does not match uploaded bytes")
        return file_id

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


def _is_text_artifact(record, registry) -> bool:
    content = registry.get(record.sha256)
    if b"\x00" in content:
        return False
    try:
        content.decode("utf-8")
    except UnicodeDecodeError:
        return False
    return True


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


def _init_delivery_outbox(database_path) -> None:
    import sqlite3
    with sqlite3.connect(str(database_path), timeout=10) as db:
        db.execute("""CREATE TABLE IF NOT EXISTS near_market_delivery_outbox (
            assignment_id TEXT PRIMARY KEY,
            task_id TEXT NOT NULL,
            markdown TEXT NOT NULL,
            state TEXT NOT NULL CHECK(state IN ('PREPARING','READY_TO_SUBMIT','SUBMITTED')),
            file_ids_json TEXT NOT NULL DEFAULT '[]',
            last_error TEXT,
            updated_at TEXT NOT NULL
        )""")
        db.execute("""CREATE TABLE IF NOT EXISTS near_market_delivery_files (
            assignment_id TEXT NOT NULL,
            artifact_sha256 TEXT NOT NULL,
            file_id TEXT NOT NULL,
            PRIMARY KEY(assignment_id, artifact_sha256),
            UNIQUE(assignment_id, file_id)
        )""")


def _persist_delivery(database_path, assignment_id: str, task_id: str, markdown: str) -> None:
    import sqlite3
    from datetime import datetime, timezone
    _init_delivery_outbox(database_path)
    with sqlite3.connect(str(database_path), timeout=10) as db:
        existing = db.execute("SELECT task_id, markdown FROM near_market_delivery_outbox WHERE assignment_id=?", (assignment_id,)).fetchone()
        if existing and existing != (task_id, markdown):
            raise NearMarketError("a different delivery is already prepared for this assignment")
        db.execute("INSERT OR IGNORE INTO near_market_delivery_outbox(assignment_id,task_id,markdown,state,updated_at) VALUES(?,?,?,'PREPARING',?)", (assignment_id, task_id, markdown, datetime.now(timezone.utc).isoformat()))


def _record_uploaded_file(database_path, assignment_id: str, digest: str, file_id: str) -> None:
    import sqlite3
    with sqlite3.connect(str(database_path), timeout=10) as db:
        db.execute("INSERT OR IGNORE INTO near_market_delivery_files(assignment_id,artifact_sha256,file_id) VALUES(?,?,?)", (assignment_id, digest, file_id))
        row = db.execute("SELECT file_id FROM near_market_delivery_files WHERE assignment_id=? AND artifact_sha256=?", (assignment_id, digest)).fetchone()
        if not row or row[0] != file_id:
            raise NearMarketError("artifact upload mapping conflicts with existing delivery state")


def _existing_uploads(database_path, assignment_id: str) -> dict[str, str]:
    import sqlite3
    with sqlite3.connect(str(database_path), timeout=10) as db:
        rows = db.execute("SELECT artifact_sha256,file_id FROM near_market_delivery_files WHERE assignment_id=?", (assignment_id,)).fetchall()
    return dict(rows)


def retry_prepared_delivery(assignment_id: str, *, database_path, lifecycle: NearMarketLifecycle) -> MarketplaceSubmission:
    """Retry only marketplace delivery; never reruns the worker."""
    import sqlite3
    _init_delivery_outbox(database_path)
    with sqlite3.connect(str(database_path), timeout=10) as db:
        row = db.execute("SELECT task_id,markdown,state FROM near_market_delivery_outbox WHERE assignment_id=?", (assignment_id,)).fetchone()
    if row is None:
        raise NearMarketError("no prepared delivery exists for this assignment")
    task_id, markdown, state = row
    if state == "SUBMITTED":
        return MarketplaceSubmission(assignment_id, "submitted", None, None)
    if state == "PREPARING":
        from ownera.artifact_registry import SQLiteArtifactRegistry
        registry = SQLiteArtifactRegistry(database_path)
        records = registry.list_for_task(task_id)
        if len(records) > MAX_MARKETPLACE_FILES:
            raise NearMarketError("assignment produced more than five files; consolidate artifacts before delivery")
        if sum(record.size_bytes for record in records) > MAX_MARKETPLACE_FILE_BYTES:
            raise NearMarketError("combined artifacts exceed marketplace 100 MiB delivery limit")
        uploaded = _existing_uploads(database_path, assignment_id)
        for record in records:
            if record.sha256 in uploaded:
                continue
            content = registry.get(record.sha256)
            file_id = lifecycle.upload_file(record.artifact_name, content, content_type=record.media_type)
            _record_uploaded_file(database_path, assignment_id, record.sha256, file_id)
            uploaded[record.sha256] = file_id
        import sqlite3
        from datetime import datetime, timezone
        with sqlite3.connect(str(database_path), timeout=10) as db:
            db.execute("UPDATE near_market_delivery_outbox SET state='READY_TO_SUBMIT',updated_at=? WHERE assignment_id=?", (datetime.now(timezone.utc).isoformat(), assignment_id))
        state = "READY_TO_SUBMIT"
    if state != "READY_TO_SUBMIT":
        raise NearMarketError("delivery is not ready to submit")
    # Resolve ambiguous timeouts by reading authoritative state before retrying.
    remote_state = lifecycle.get_assignment_status(assignment_id)
    if remote_state == "submitted":
        _mark_delivery_submitted(database_path, assignment_id)
        return MarketplaceSubmission(assignment_id, "submitted", None, None)
    if remote_state != "in_progress":
        raise NearMarketError(f"assignment cannot accept delivery in remote state {remote_state}")
    files = tuple(file_id for _, file_id in sorted(_existing_uploads(database_path, assignment_id).items()))
    result = lifecycle.submit_deliverable(assignment_id, markdown, files=files)
    _mark_delivery_submitted(database_path, assignment_id)
    return result


def _mark_delivery_submitted(database_path, assignment_id: str) -> None:
    import sqlite3
    from datetime import datetime, timezone
    with sqlite3.connect(str(database_path), timeout=10) as db:
        db.execute("UPDATE near_market_delivery_outbox SET state='SUBMITTED',last_error=NULL,updated_at=? WHERE assignment_id=?", (datetime.now(timezone.utc).isoformat(), assignment_id))


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
    records = local_submission.artifact_records
    if len(records) > MAX_MARKETPLACE_FILES:
        raise NearMarketError("assignment produced more than five files; consolidate artifacts before delivery")
    markdown = _compose_text_deliverable(
        spec.summary, tuple(record for record in records if _is_text_artifact(record, registry)), registry
    )
    _persist_delivery(database_path, assignment_id, spec.request.task_id, markdown)
    remote_submission = retry_prepared_delivery(assignment_id, database_path=database_path, lifecycle=lifecycle)
    return local_submission, remote_submission


def retry_pending_deliveries(database_path, *, lifecycle: NearMarketLifecycle | None = None) -> dict:
    """Reconcile/retry durable deliveries without starting or rerunning workers."""
    import sqlite3

    _init_delivery_outbox(database_path)
    with sqlite3.connect(str(database_path), timeout=10) as db:
        rows = db.execute(
            "SELECT assignment_id,state FROM near_market_delivery_outbox "
            "WHERE state IN ('PREPARING','READY_TO_SUBMIT') ORDER BY updated_at"
        ).fetchall()
    api = lifecycle or NearMarketLifecycle()
    completed = []
    failures = []
    for assignment_id, state in rows:
        try:
            result = retry_prepared_delivery(assignment_id, database_path=database_path, lifecycle=api)
            completed.append({"assignment_id": assignment_id, "status": result.status})
        except (NearMarketError, OSError, ValueError, RuntimeError, sqlite3.Error) as exc:  # Keep later deliveries moving; expose bounded error text.
            failures.append({"assignment_id": assignment_id, "state": state, "error": f"{type(exc).__name__}: {str(exc)[:300]}"})
    return {
        "schema": "ownera.near-market-delivery-retry.v1",
        "pending": len(rows),
        "completed": completed,
        "failures": failures,
        "worker_execution": "none",
    }
