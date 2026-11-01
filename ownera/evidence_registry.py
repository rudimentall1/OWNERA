"""Owner-reviewed evidence registry for commercial opportunities.

Public listing content is untrusted input. HTTPS transport and content hashes do
not prove source legitimacy, ownership, eligibility, or payment. Evidence starts
PENDING and can be accepted only through the authenticated owner review boundary.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from urllib.parse import urlparse
from uuid import UUID, uuid4

from ownera.owner_control import (
    AuthenticatedPrincipal,
    CredentialAuthenticator,
    OwnerControlError,
)


class EvidenceRegistryError(RuntimeError):
    """Base error for commercial evidence operations."""


class EvidenceIntegrityError(EvidenceRegistryError):
    """Stored evidence or its audit history failed integrity verification."""


class EvidenceStatus(str, Enum):
    PENDING = "PENDING"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"


@dataclass(frozen=True)
class OpportunityEvidence:
    evidence_id: UUID
    opportunity_id: UUID
    source_name: str
    source_url: str
    captured_at: datetime
    content_snapshot: str
    content_sha256: str
    status: EvidenceStatus
    reviewed_by: str | None
    reviewed_at: datetime | None
    review_note: str | None


class SQLiteOpportunityEvidenceRegistry:
    """Single-node SQLite registry with immutable snapshots and a hash-chained audit."""

    MAX_SNAPSHOT_CHARS = 16_384
    GENESIS_HASH = "0" * 64

    def __init__(
        self,
        database_path: str | Path,
        authenticator: CredentialAuthenticator,
    ) -> None:
        self.database_path = str(database_path)
        if self.database_path == ":memory:":
            raise ValueError("evidence registry requires a file-backed database")
        self._authenticator = authenticator
        Path(self.database_path).parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS opportunity_evidence (
                    evidence_id TEXT PRIMARY KEY,
                    opportunity_id TEXT NOT NULL,
                    source_name TEXT NOT NULL,
                    source_url TEXT NOT NULL,
                    captured_at TEXT NOT NULL,
                    content_snapshot TEXT NOT NULL,
                    content_sha256 TEXT NOT NULL,
                    status TEXT NOT NULL CHECK(status IN ('PENDING','ACCEPTED','REJECTED')),
                    reviewed_by TEXT,
                    reviewed_at TEXT,
                    review_note TEXT
                )
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_opportunity_evidence_opportunity
                ON opportunity_evidence(opportunity_id, captured_at)
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS opportunity_evidence_events (
                    event_id TEXT PRIMARY KEY,
                    evidence_id TEXT NOT NULL,
                    version INTEGER NOT NULL CHECK(version > 0),
                    event_type TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    occurred_at TEXT NOT NULL,
                    idempotency_key TEXT UNIQUE,
                    previous_hash TEXT NOT NULL,
                    event_hash TEXT NOT NULL,
                    UNIQUE(evidence_id, version),
                    FOREIGN KEY(evidence_id) REFERENCES opportunity_evidence(evidence_id)
                )
                """
            )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(
            self.database_path, timeout=10, isolation_level=None
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 10000")
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA synchronous = FULL")
        return connection

    @staticmethod
    def _canonical(value: dict) -> str:
        return json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
            allow_nan=False,
        )

    @staticmethod
    def _content_digest(content: str) -> str:
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    def _append_event(
        self,
        connection: sqlite3.Connection,
        *,
        evidence_id: UUID,
        event_type: str,
        payload: dict,
        occurred_at: datetime,
        idempotency_key: str,
    ) -> None:
        latest = connection.execute(
            """
            SELECT version, event_hash FROM opportunity_evidence_events
            WHERE evidence_id = ? ORDER BY version DESC LIMIT 1
            """,
            (str(evidence_id),),
        ).fetchone()
        version = latest["version"] + 1 if latest else 1
        previous_hash = latest["event_hash"] if latest else self.GENESIS_HASH
        event_id = str(uuid4())
        payload_json = self._canonical(payload)
        occurred_text = occurred_at.astimezone(timezone.utc).isoformat()
        hash_input = {
            "event_id": event_id,
            "evidence_id": str(evidence_id),
            "version": version,
            "event_type": event_type,
            "payload_json": payload_json,
            "occurred_at": occurred_text,
            "idempotency_key": idempotency_key,
            "previous_hash": previous_hash,
        }
        event_hash = hashlib.sha256(
            self._canonical(hash_input).encode("utf-8")
        ).hexdigest()
        connection.execute(
            """
            INSERT INTO opportunity_evidence_events(
                event_id,evidence_id,version,event_type,payload_json,occurred_at,
                idempotency_key,previous_hash,event_hash
            ) VALUES(?,?,?,?,?,?,?,?,?)
            """,
            (
                event_id, str(evidence_id), version, event_type, payload_json,
                occurred_text, idempotency_key, previous_hash, event_hash,
            ),
        )

    def capture(
        self,
        *,
        opportunity_id: UUID,
        source_name: str,
        source_url: str,
        content_snapshot: str,
        captured_at: datetime | None = None,
        evidence_id: UUID | None = None,
    ) -> OpportunityEvidence:
        if not source_name.strip():
            raise ValueError("source_name is required")
        parsed = urlparse(source_url)
        if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password:
            raise ValueError("source_url must be an absolute HTTPS URL without credentials")
        if not isinstance(content_snapshot, str) or not content_snapshot.strip():
            raise ValueError("content_snapshot is required")
        if len(content_snapshot) > self.MAX_SNAPSHOT_CHARS:
            raise ValueError("content_snapshot exceeds the maximum allowed size")
        timestamp = captured_at or datetime.now(timezone.utc)
        if timestamp.tzinfo is None:
            raise ValueError("captured_at must be timezone-aware")
        timestamp = timestamp.astimezone(timezone.utc)
        item_id = evidence_id or uuid4()
        digest = self._content_digest(content_snapshot)
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                """
                INSERT INTO opportunity_evidence(
                    evidence_id,opportunity_id,source_name,source_url,captured_at,
                    content_snapshot,content_sha256,status
                ) VALUES(?,?,?,?,?,?,?,'PENDING')
                """,
                (
                    str(item_id), str(opportunity_id), source_name.strip(),
                    source_url, timestamp.isoformat(), content_snapshot, digest,
                ),
            )
            self._append_event(
                connection,
                evidence_id=item_id,
                event_type="EvidenceCaptured",
                payload={
                    "opportunity_id": str(opportunity_id),
                    "source_name": source_name.strip(),
                    "source_url": source_url,
                    "captured_at": timestamp.isoformat(),
                    "content_sha256": digest,
                    "content_chars": len(content_snapshot),
                    "status": EvidenceStatus.PENDING.value,
                },
                occurred_at=timestamp,
                idempotency_key=f"capture:{item_id}:{digest}",
            )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()
        return self.get(item_id)

    def _owner(self, credential: str) -> AuthenticatedPrincipal:
        if not isinstance(credential, str) or not credential.strip():
            raise OwnerControlError("owner credential is required")
        try:
            principal = self._authenticator.authenticate(credential)
        except Exception as exc:
            raise OwnerControlError("owner authentication failed") from exc
        if not isinstance(principal, AuthenticatedPrincipal):
            raise OwnerControlError("authenticator returned an invalid principal")
        now = datetime.now(timezone.utc)
        if (
            not principal.issuer.strip()
            or not principal.subject.strip()
            or not principal.session_id.strip()
            or not principal.authentication_method.strip()
            or principal.expires_at.tzinfo is None
            or principal.expires_at <= now
            or principal.authenticated_at.tzinfo is None
            or principal.authenticated_at > now
        ):
            raise OwnerControlError("authenticated principal is invalid or expired")
        if "owner:commercial" not in principal.roles:
            raise OwnerControlError("owner commercial review permission required")
        return principal

    def review(
        self,
        credential: str,
        evidence_id: UUID,
        *,
        accept: bool,
        note: str = "",
        now: datetime | None = None,
    ) -> OpportunityEvidence:
        if not isinstance(accept, bool):
            raise TypeError("accept must be a boolean")
        if len(note) > 2_000:
            raise ValueError("review note exceeds the maximum allowed size")
        owner = self._owner(credential)
        timestamp = now or datetime.now(timezone.utc)
        if timestamp.tzinfo is None or timestamp > datetime.now(timezone.utc):
            raise ValueError("review timestamp must be timezone-aware and not in the future")
        timestamp = timestamp.astimezone(timezone.utc)
        status = EvidenceStatus.ACCEPTED if accept else EvidenceStatus.REJECTED
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT * FROM opportunity_evidence WHERE evidence_id = ?",
                (str(evidence_id),),
            ).fetchone()
            if row is None:
                raise EvidenceRegistryError("evidence does not exist")
            if row["status"] != EvidenceStatus.PENDING.value:
                raise EvidenceRegistryError("only pending evidence can be reviewed")
            actual_digest = self._content_digest(row["content_snapshot"])
            if actual_digest != row["content_sha256"]:
                raise EvidenceIntegrityError("evidence content digest mismatch")
            connection.execute(
                """
                UPDATE opportunity_evidence
                SET status=?, reviewed_by=?, reviewed_at=?, review_note=?
                WHERE evidence_id=? AND status='PENDING'
                """,
                (status.value, owner.subject, timestamp.isoformat(), note.strip(), str(evidence_id)),
            )
            self._append_event(
                connection,
                evidence_id=evidence_id,
                event_type="EvidenceReviewed",
                payload={
                    "status": status.value,
                    "reviewed_by": owner.subject,
                    "reviewed_at": timestamp.isoformat(),
                    "review_note": note.strip(),
                    "content_sha256": actual_digest,
                },
                occurred_at=timestamp,
                idempotency_key=f"review:{evidence_id}:{status.value}:{owner.subject}",
            )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()
        return self.get(evidence_id)

    def get(self, evidence_id: UUID) -> OpportunityEvidence:
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT * FROM opportunity_evidence WHERE evidence_id=?",
                (str(evidence_id),),
            ).fetchone()
        finally:
            connection.close()
        if row is None:
            raise EvidenceRegistryError("evidence does not exist")
        return OpportunityEvidence(
            evidence_id=UUID(row["evidence_id"]),
            opportunity_id=UUID(row["opportunity_id"]),
            source_name=row["source_name"],
            source_url=row["source_url"],
            captured_at=datetime.fromisoformat(row["captured_at"]),
            content_snapshot=row["content_snapshot"],
            content_sha256=row["content_sha256"],
            status=EvidenceStatus(row["status"]),
            reviewed_by=row["reviewed_by"],
            reviewed_at=datetime.fromisoformat(row["reviewed_at"]) if row["reviewed_at"] else None,
            review_note=row["review_note"],
        )

    def require_accepted(
        self,
        opportunity_id: UUID,
        evidence_refs: tuple[str, ...],
        *,
        expected_source_url: str | None = None,
    ) -> None:
        """Fail closed unless evidence is accepted and bound to this opportunity."""
        if not evidence_refs:
            raise EvidenceRegistryError("at least one accepted evidence reference is required")
        primary_source_matched = expected_source_url is None
        for reference in evidence_refs:
            try:
                evidence_id = UUID(reference)
            except (TypeError, ValueError) as exc:
                raise EvidenceRegistryError("evidence references must be registry UUIDs") from exc
            item = self.get(evidence_id)
            if item.opportunity_id != opportunity_id:
                raise EvidenceRegistryError("evidence belongs to a different opportunity")
            if item.status is not EvidenceStatus.ACCEPTED:
                raise EvidenceRegistryError("evidence has not been accepted by the owner")
            if expected_source_url is not None and item.source_url == expected_source_url:
                primary_source_matched = True
            self.verify(evidence_id)
        if not primary_source_matched:
            raise EvidenceRegistryError(
                "accepted evidence does not match the opportunity source URL"
            )

    def verify(self, evidence_id: UUID) -> bool:
        item = self.get(evidence_id)
        if self._content_digest(item.content_snapshot) != item.content_sha256:
            raise EvidenceIntegrityError("evidence content digest mismatch")
        connection = self._connect()
        try:
            rows = connection.execute(
                """
                SELECT * FROM opportunity_evidence_events
                WHERE evidence_id=? ORDER BY version
                """,
                (str(evidence_id),),
            ).fetchall()
        finally:
            connection.close()
        previous_hash = self.GENESIS_HASH
        if not rows:
            raise EvidenceIntegrityError("evidence audit history is missing")
        for expected_version, row in enumerate(rows, start=1):
            if row["version"] != expected_version or row["previous_hash"] != previous_hash:
                raise EvidenceIntegrityError("evidence audit chain sequence mismatch")
            hash_input = {
                "event_id": row["event_id"],
                "evidence_id": row["evidence_id"],
                "version": row["version"],
                "event_type": row["event_type"],
                "payload_json": row["payload_json"],
                "occurred_at": row["occurred_at"],
                "idempotency_key": row["idempotency_key"],
                "previous_hash": row["previous_hash"],
            }
            actual = hashlib.sha256(
                self._canonical(hash_input).encode("utf-8")
            ).hexdigest()
            if actual != row["event_hash"]:
                raise EvidenceIntegrityError("evidence audit event hash mismatch")
            previous_hash = actual
        capture = json.loads(rows[0]["payload_json"])
        if (
            rows[0]["event_type"] != "EvidenceCaptured"
            or capture.get("opportunity_id") != str(item.opportunity_id)
            or capture.get("source_name") != item.source_name
            or capture.get("source_url") != item.source_url
            or capture.get("captured_at") != item.captured_at.isoformat()
            or capture.get("content_sha256") != item.content_sha256
        ):
            raise EvidenceIntegrityError("evidence row does not match capture event")
        if len(rows) not in (1, 2):
            raise EvidenceIntegrityError("evidence audit contains an invalid event sequence")
        if len(rows) == 1:
            if (
                item.status is not EvidenceStatus.PENDING
                or item.reviewed_by is not None
                or item.reviewed_at is not None
                or item.review_note is not None
            ):
                raise EvidenceIntegrityError("evidence row has review fields without a review event")
        else:
            review = json.loads(rows[1]["payload_json"])
            if (
                rows[1]["event_type"] != "EvidenceReviewed"
                or review.get("status") != item.status.value
                or review.get("reviewed_by") != item.reviewed_by
                or review.get("reviewed_at") != (
                    item.reviewed_at.isoformat() if item.reviewed_at else None
                )
                or review.get("review_note") != (item.review_note or "")
                or review.get("content_sha256") != item.content_sha256
                or item.status is EvidenceStatus.PENDING
            ):
                raise EvidenceIntegrityError("evidence row does not match review event")
        return True
