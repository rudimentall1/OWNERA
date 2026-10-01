"""Verigate authority adapter for OWNERA financial execution.

The adapter is intentionally transport-agnostic. Production deployments can
use the HTTP transport, while tests can inject an in-process transport. The
financial action digest is carried inside the signed Verigate ActionIntent
metadata and must match exactly before the authorization crosses back into
OWNERA.
"""

from __future__ import annotations

import base64
import hashlib
import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Protocol
from uuid import UUID

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from .authorization import AuthorizationError, ExecutionAuthorization
from .domain import Decision, PaymentIntent
from .financial_action import FinancialAction
from .firewall import AuthorizationDecision


class VerigateTransport(Protocol):
    def request(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        ...


@dataclass(frozen=True)
class HttpVerigateTransport:
    """Minimal dependency-free JSON transport for a Verigate deployment."""

    base_url: str
    timeout_seconds: float = 10.0

    def request(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        body = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        request = urllib.request.Request(
            self.base_url.rstrip("/") + path,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                raw = response.read()
        except urllib.error.URLError as exc:
            raise AuthorizationError(f"Verigate request failed: {exc}") from exc
        try:
            decoded = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise AuthorizationError("Verigate returned invalid JSON") from exc
        if not isinstance(decoded, dict):
            raise AuthorizationError("Verigate returned a non-object response")
        return decoded


def _canonical(payload: dict[str, Any]) -> bytes:
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def _verify_signature(envelope: dict[str, Any], public_key: Ed25519PublicKey) -> None:
    if envelope.get("algorithm") != "Ed25519":
        raise AuthorizationError("unsupported Verigate signature algorithm")
    payload = envelope.get("payload")
    signature = envelope.get("signature")
    if not isinstance(payload, dict) or not isinstance(signature, str):
        raise AuthorizationError("malformed Verigate authorization envelope")
    try:
        public_key.verify(base64.b64decode(signature, validate=True), _canonical(payload))
    except (InvalidSignature, ValueError) as exc:
        raise AuthorizationError("invalid Verigate authorization signature") from exc


def _require_fingerprint(value: Any, field: str) -> str:
    if not isinstance(value, str) or len(value) != 64:
        raise AuthorizationError(f"invalid Verigate authorization field: {field}")
    if any(char not in "0123456789abcdef" for char in value):
        raise AuthorizationError(f"invalid Verigate authorization field: {field}")
    return value


def _parse_datetime(value: Any, field: str) -> datetime:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise AuthorizationError(f"invalid Verigate authorization field: {field}")
    return datetime.fromtimestamp(value, tz=timezone.utc)


def _build_verigate_action(
    financial_action: FinancialAction,
    *,
    metadata: dict[str, Any],
    intent_id: str,
) -> dict[str, Any]:
    merged_metadata = {
        **metadata,
        "ownera_financial_action_sha256": financial_action.digest(),
    }
    return {
        "agent_id": financial_action.agent_id,
        "action_type": financial_action.action_type,
        "target": financial_action.destination,
        "resource": "",
        "amount": None,
        "amount_exact": format(financial_action.amount, "f"),
        "asset": financial_action.currency,
        "network": None,
        "purpose": financial_action.purpose,
        "declared_context": {},
        "input_provenance": {},
        "parent_intent_id": None,
        "requested_capability": None,
        "constraints": {},
        "metadata": merged_metadata,
        "intent_id": intent_id,
        "timestamp": datetime.now(timezone.utc).timestamp(),
    }


@dataclass
class VerigateAuthorityAdapter:
    """OWNERA AuthorityPort implementation backed by Verigate."""

    transport: VerigateTransport
    issuer_public_key: Ed25519PublicKey
    agent_id: str
    identity_id: str
    capability_id: str
    sign_action: Callable[[dict[str, Any]], str]
    consumed: set[str]

    @classmethod
    def create(
        cls,
        transport: VerigateTransport,
        issuer_public_key: Ed25519PublicKey,
        *,
        agent_id: str,
        identity_id: str,
        capability_id: str,
        sign_action: Callable[[dict[str, Any]], str],
    ) -> VerigateAuthorityAdapter:
        if not agent_id.strip():
            raise ValueError("agent_id is required")
        return cls(
            transport=transport,
            issuer_public_key=issuer_public_key,
            agent_id=agent_id,
            identity_id=identity_id,
            capability_id=capability_id,
            sign_action=sign_action,
            consumed=set(),
        )

    def issue(
        self,
        intent: PaymentIntent,
        verdict: AuthorizationDecision,
        *,
        policy_version: str,
        now: datetime | None = None,
    ) -> ExecutionAuthorization:
        if verdict.decision != Decision.ALLOW:
            raise AuthorizationError("only ALLOW verdicts can be authorized")
        if intent.idempotency_key == "":
            raise AuthorizationError("idempotency key is required")

        financial_action = intent.to_financial_action(self.agent_id)
        action = _build_verigate_action(
            financial_action,
            metadata={"ownera_policy_version": policy_version},
            intent_id=str(intent.id),
        )
        agent_signature = self.sign_action(action)
        response = self.transport.request(
            "/v1/actions/authorize",
            {
                "identity_id": self.identity_id,
                "capability_id": self.capability_id,
                "agent_id": self.agent_id,
                "agent_signature": agent_signature,
                "intent_id": action["intent_id"],
                "timestamp": action["timestamp"],
                "action_type": action["action_type"],
                "target": action["target"],
                "resource": action["resource"],
                "amount": None,
                "amount_exact": action["amount_exact"],
                "asset": action["asset"],
                "network": None,
                "purpose": action["purpose"],
                "declared_context": {},
                "parent_intent_id": None,
                "requested_capability": None,
                "constraints": {},
                "metadata": action["metadata"],
            },
        )
        authorization = response.get("execution_authorization")
        if authorization is None:
            raise AuthorizationError("Verigate did not issue execution authority")

        _verify_signature(authorization, self.issuer_public_key)
        payload = authorization["payload"]
        if payload.get("intent_id") != str(intent.id):
            raise AuthorizationError("Verigate authorization intent mismatch")
        if payload.get("agent_id") != self.agent_id:
            raise AuthorizationError("Verigate authorization agent mismatch")

        authorized_action = payload.get("action")
        if not isinstance(authorized_action, dict):
            raise AuthorizationError("Verigate authorization is missing exact action")
        if authorized_action.get("intent_id") != str(intent.id):
            raise AuthorizationError("Verigate action intent mismatch")
        if authorized_action.get("amount_exact") != action["amount_exact"]:
            raise AuthorizationError("Verigate exact amount mismatch")
        if authorized_action.get("target") != action["target"]:
            raise AuthorizationError("Verigate destination mismatch")
        metadata = authorized_action.get("metadata")
        if not isinstance(metadata, dict):
            raise AuthorizationError("Verigate action metadata is malformed")
        if metadata.get("ownera_financial_action_sha256") != financial_action.digest():
            raise AuthorizationError("Verigate financial action digest mismatch")

        issued_at = _parse_datetime(payload.get("issued_at"), "issued_at")
        expires_at = _parse_datetime(payload.get("expires_at"), "expires_at")
        authorization_id = _require_fingerprint(payload.get("authorization_id"), "authorization_id")

        # Verigate's authorization_id is normally a SHA-256 fingerprint rather
        # than a UUID. Keep the local artifact identifier stable by deriving a
        # UUID from that signed identifier; the signed provider artifact remains
        # available through provider_authorization below.
        local_id = UUID(bytes=hashlib.sha256(authorization_id.encode()).digest()[:16])
        correlation_id = verdict.correlation_id
        return ExecutionAuthorization(
            id=local_id,
            intent_id=intent.id,
            correlation_id=correlation_id,
            policy_version=policy_version,
            issued_at=issued_at,
            expires_at=expires_at,
            nonce=payload.get("nonce", ""),
            provider="verigate",
            provider_authorization=authorization,
        )

    def consume(
        self,
        authorization: ExecutionAuthorization,
        intent: PaymentIntent,
        *,
        now: datetime | None = None,
    ) -> None:
        if authorization.provider != "verigate" or authorization.provider_authorization is None:
            raise AuthorizationError("authorization is not a Verigate artifact")
        if authorization.intent_id != intent.id:
            raise AuthorizationError("authorization intent mismatch")
        current = now or datetime.now(timezone.utc)
        if not authorization.is_valid_at(current):
            raise AuthorizationError("authorization expired or not yet valid")
        if str(authorization.id) in self.consumed:
            raise AuthorizationError("authorization already consumed")

        response = self.transport.request(
            "/v1/execution/consume",
            {"authorization": authorization.provider_authorization},
        )
        if response.get("execute") is not True:
            raise AuthorizationError(
                f"Verigate rejected execution authority: {response.get('reason', 'unknown reason')}"
            )
        self.consumed.add(str(authorization.id))
