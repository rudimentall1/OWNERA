"""Durable Ed25519 customer key registry with an append-only audit chain.

Enrollment is an owner/admin trust decision. This module records who performed
that decision but does not authenticate the actor; production must put an
authenticated administrative boundary in front of these methods.
"""
from __future__ import annotations

import base64
import hashlib
import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey


class AcceptanceVerificationError(ValueError):
    """An acceptance attestation cannot be trusted."""


class TrustedKeyRegistryError(RuntimeError):
    """A trusted-key registry operation failed."""


@dataclass(frozen=True)
class CustomerAcceptanceAttestation:
    key_id: str
    signature_b64: str
    nonce: str


@dataclass(frozen=True)
class TrustedCustomerKey:
    customer_id: str
    key_id: str
    public_key_b64: str
    active: bool = True


@dataclass(frozen=True)
class AcceptanceVerification:
    status: str
    key_id: str | None
    attestation_digest: str | None
    reason: str


class TrustedCustomerKeyRegistry:
    """SQLite-backed registry. A file path survives process restarts."""

    GENESIS = "0" * 64

    def __init__(self, database_path: str | Path = ":memory:") -> None:
        self.database_path = str(database_path)
        if self.database_path != ":memory:":
            Path(self.database_path).parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(
            self.database_path, timeout=10, isolation_level=None
        )
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA busy_timeout = 10000")
        if self.database_path != ":memory:":
            self._connection.execute("PRAGMA journal_mode = WAL")
            self._connection.execute("PRAGMA synchronous = FULL")
        self._connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS trusted_customer_keys (
                customer_id TEXT NOT NULL,
                key_id TEXT NOT NULL,
                public_key_b64 TEXT NOT NULL,
                active INTEGER NOT NULL CHECK(active IN (0, 1)),
                enrolled_at TEXT NOT NULL,
                revoked_at TEXT,
                PRIMARY KEY(customer_id, key_id)
            );
            CREATE TABLE IF NOT EXISTS trusted_key_audit (
                sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                event_type TEXT NOT NULL,
                customer_id TEXT NOT NULL,
                key_id TEXT NOT NULL,
                actor_id TEXT NOT NULL,
                occurred_at TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                previous_hash TEXT NOT NULL,
                event_hash TEXT NOT NULL UNIQUE
            );
            """
        )

    def close(self) -> None:
        self._connection.close()

    def __enter__(self) -> "TrustedCustomerKeyRegistry":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    @staticmethod
    def _canonical(payload: dict[str, object]) -> str:
        return json.dumps(
            payload, sort_keys=True, separators=(",", ":"),
            ensure_ascii=False, allow_nan=False,
        )

    def _append_audit(
        self, event_type: str, customer_id: str, key_id: str,
        actor_id: str, payload: dict[str, object],
    ) -> None:
        previous = self._connection.execute(
            "SELECT event_hash FROM trusted_key_audit ORDER BY sequence DESC LIMIT 1"
        ).fetchone()
        previous_hash = previous["event_hash"] if previous else self.GENESIS
        occurred_at = datetime.now(timezone.utc).isoformat()
        payload_json = self._canonical(payload)
        body = self._canonical({
            "event_type": event_type, "customer_id": customer_id,
            "key_id": key_id, "actor_id": actor_id,
            "occurred_at": occurred_at, "payload_json": payload_json,
            "previous_hash": previous_hash,
        })
        event_hash = hashlib.sha256(body.encode("utf-8")).hexdigest()
        self._connection.execute(
            """INSERT INTO trusted_key_audit
               (event_type, customer_id, key_id, actor_id, occurred_at,
                payload_json, previous_hash, event_hash)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (event_type, customer_id, key_id, actor_id, occurred_at,
             payload_json, previous_hash, event_hash),
        )

    def enroll(
        self, customer_id: str, key_id: str, public_key: bytes,
        *, actor_id: str = "owner",
    ) -> None:
        if not customer_id.strip() or not key_id.strip() or not actor_id.strip():
            raise ValueError("customer_id, key_id, and actor_id are required")
        if len(public_key) != 32:
            raise ValueError("Ed25519 public keys must be 32 bytes")
        encoded = base64.b64encode(public_key).decode("ascii")
        now = datetime.now(timezone.utc).isoformat()
        self._connection.execute("BEGIN IMMEDIATE")
        try:
            self._connection.execute(
                """INSERT INTO trusted_customer_keys
                   (customer_id, key_id, public_key_b64, active, enrolled_at)
                   VALUES (?, ?, ?, 1, ?)""",
                (customer_id, key_id, encoded, now),
            )
            self._append_audit(
                "KEY_ENROLLED", customer_id, key_id, actor_id,
                {"public_key_sha256": hashlib.sha256(public_key).hexdigest()},
            )
            self._connection.commit()
        except Exception:
            self._connection.rollback()
            raise

    def revoke(
        self, customer_id: str, key_id: str, *, actor_id: str = "owner",
    ) -> None:
        if not actor_id.strip():
            raise ValueError("actor_id is required")
        self._connection.execute("BEGIN IMMEDIATE")
        try:
            cursor = self._connection.execute(
                """UPDATE trusted_customer_keys SET active = 0, revoked_at = ?
                   WHERE customer_id = ? AND key_id = ? AND active = 1""",
                (datetime.now(timezone.utc).isoformat(), customer_id, key_id),
            )
            if cursor.rowcount != 1:
                raise KeyError("active trusted customer key not found")
            self._append_audit(
                "KEY_REVOKED", customer_id, key_id, actor_id, {},
            )
            self._connection.commit()
        except Exception:
            self._connection.rollback()
            raise

    def rotate(
        self, customer_id: str, old_key_id: str, new_key_id: str,
        new_public_key: bytes, *, actor_id: str = "owner",
    ) -> None:
        """Atomically enroll a replacement and revoke the previous active key."""
        if not actor_id.strip() or not customer_id.strip() or not new_key_id.strip():
            raise ValueError("customer_id, new_key_id, and actor_id are required")
        if len(new_public_key) != 32:
            raise ValueError("Ed25519 public keys must be 32 bytes")
        encoded = base64.b64encode(new_public_key).decode("ascii")
        now = datetime.now(timezone.utc).isoformat()
        self._connection.execute("BEGIN IMMEDIATE")
        try:
            cursor = self._connection.execute(
                """UPDATE trusted_customer_keys SET active = 0, revoked_at = ?
                   WHERE customer_id = ? AND key_id = ? AND active = 1""",
                (now, customer_id, old_key_id),
            )
            if cursor.rowcount != 1:
                raise KeyError("active trusted customer key not found")
            self._append_audit("KEY_REVOKED", customer_id, old_key_id, actor_id,
                               {"rotation_replacement": new_key_id})
            self._connection.execute(
                """INSERT INTO trusted_customer_keys
                   (customer_id, key_id, public_key_b64, active, enrolled_at)
                   VALUES (?, ?, ?, 1, ?)""",
                (customer_id, new_key_id, encoded, now),
            )
            self._append_audit(
                "KEY_ENROLLED", customer_id, new_key_id, actor_id,
                {"public_key_sha256": hashlib.sha256(new_public_key).hexdigest(),
                 "rotation_previous": old_key_id},
            )
            self._connection.commit()
        except Exception:
            self._connection.rollback()
            raise

    def verify_registry_integrity(self) -> bool:
        """Verify the audit chain and ensure key rows match audited lifecycle state."""
        self.verify_audit_chain()
        expected: dict[tuple[str, str], dict[str, object]] = {}
        for event in self.audit_events():
            identity = (str(event["customer_id"]), str(event["key_id"]))
            payload = json.loads(str(event["payload_json"]))
            if event["event_type"] == "KEY_ENROLLED":
                expected[identity] = {
                    "active": True,
                    "public_key_sha256": payload["public_key_sha256"],
                }
            elif event["event_type"] == "KEY_REVOKED":
                if identity not in expected or not expected[identity]["active"]:
                    raise TrustedKeyRegistryError("audit contains an invalid key revocation")
                expected[identity]["active"] = False
            else:
                raise TrustedKeyRegistryError("audit contains an unknown key lifecycle event")
        rows = self._connection.execute(
            "SELECT customer_id, key_id, public_key_b64, active FROM trusted_customer_keys"
        ).fetchall()
        actual = {(row["customer_id"], row["key_id"]): row for row in rows}
        if set(actual) != set(expected):
            raise TrustedKeyRegistryError("trusted-key records do not match audit history")
        for identity, state in expected.items():
            row = actual[identity]
            fingerprint = hashlib.sha256(
                base64.b64decode(row["public_key_b64"], validate=True)
            ).hexdigest()
            if fingerprint != state["public_key_sha256"] or bool(row["active"]) != state["active"]:
                raise TrustedKeyRegistryError("trusted-key record differs from audit history")
        return True

    def get_active(self, customer_id: str, key_id: str) -> TrustedCustomerKey:
        self.verify_registry_integrity()
        row = self._connection.execute(
            """SELECT customer_id, key_id, public_key_b64, active
               FROM trusted_customer_keys WHERE customer_id = ? AND key_id = ?""",
            (customer_id, key_id),
        ).fetchone()
        if row is None or not row["active"]:
            raise AcceptanceVerificationError("trusted customer key is missing or revoked")
        return TrustedCustomerKey(
            row["customer_id"], row["key_id"], row["public_key_b64"], True
        )

    def audit_events(self) -> tuple[dict[str, object], ...]:
        rows = self._connection.execute(
            "SELECT * FROM trusted_key_audit ORDER BY sequence"
        ).fetchall()
        return tuple(dict(row) for row in rows)

    def verify_audit_chain(self) -> bool:
        previous_hash = self.GENESIS
        rows = self._connection.execute(
            "SELECT * FROM trusted_key_audit ORDER BY sequence"
        ).fetchall()
        for row in rows:
            if row["previous_hash"] != previous_hash:
                raise TrustedKeyRegistryError("trusted-key audit chain is broken")
            body = self._canonical({
                "event_type": row["event_type"],
                "customer_id": row["customer_id"],
                "key_id": row["key_id"],
                "actor_id": row["actor_id"],
                "occurred_at": row["occurred_at"],
                "payload_json": row["payload_json"],
                "previous_hash": row["previous_hash"],
            })
            expected = hashlib.sha256(body.encode("utf-8")).hexdigest()
            if expected != row["event_hash"]:
                raise TrustedKeyRegistryError("trusted-key audit event digest mismatch")
            previous_hash = row["event_hash"]
        return True


def acceptance_signing_payload(order: object) -> bytes:
    attestation = order.acceptance_attestation
    payload = {
        "schema_version": 1,
        "customer_id": order.customer_id,
        "order_id": str(order.order_id),
        "proposal_id": str(order.proposal_id),
        "accepted_amount": str(order.accepted_amount),
        "currency": order.currency.upper(),
        "customer_acceptance_reference": order.customer_acceptance_ref,
        "accepted_scope": order.accepted_scope,
        "accepted_acceptance_criteria": list(order.accepted_acceptance_criteria),
        "customer_accepted_at": order.customer_accepted_at.astimezone(timezone.utc).isoformat(),
        "nonce": attestation.nonce,
    }
    return json.dumps(
        payload, sort_keys=True, separators=(",", ":"),
        ensure_ascii=False, allow_nan=False,
    ).encode("utf-8")


def verify_customer_acceptance(
    order: object, registry: TrustedCustomerKeyRegistry,
) -> AcceptanceVerification:
    attestation = order.acceptance_attestation
    if attestation is None:
        raise AcceptanceVerificationError("customer acceptance attestation is missing")
    if not attestation.nonce.strip():
        raise AcceptanceVerificationError("attestation nonce is required")
    trusted = registry.get_active(order.customer_id, attestation.key_id)
    try:
        key = Ed25519PublicKey.from_public_bytes(
            base64.b64decode(trusted.public_key_b64, validate=True)
        )
        signature = base64.b64decode(attestation.signature_b64, validate=True)
        key.verify(signature, acceptance_signing_payload(order))
    except (InvalidSignature, ValueError) as exc:
        raise AcceptanceVerificationError("customer acceptance signature is invalid") from exc
    canonical = json.dumps(
        {"key_id": attestation.key_id, "nonce": attestation.nonce,
         "signature_b64": attestation.signature_b64},
        sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    )
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return AcceptanceVerification("VERIFIED", attestation.key_id, digest, "signature_valid")
