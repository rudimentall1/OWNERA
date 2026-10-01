"""Explicit authorization lifecycle for OWNERA financial actions.

Authorization is a short-lived, immutable decision artifact. It is not a
capability tier and it never grants access to the Sovereign Reserve.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from .domain import Decision, PaymentIntent
from .firewall import AuthorizationDecision


class AuthorizationError(PermissionError):
    """Raised when an authorization cannot be issued or consumed."""


@dataclass(frozen=True)
class ExecutionAuthorization:
    id: UUID
    intent_id: UUID
    correlation_id: UUID
    policy_version: str
    issued_at: datetime
    expires_at: datetime
    nonce: str

    def is_valid_at(self, now: datetime | None = None) -> bool:
        now = now or datetime.now(timezone.utc)
        return self.issued_at <= now < self.expires_at


class AuthorizationIssuer:
    """Issues one-shot authorization artifacts from an ALLOW verdict."""

    def __init__(self, ttl_seconds: int = 60) -> None:
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be positive")
        self._ttl = timedelta(seconds=ttl_seconds)
        self._consumed: set[UUID] = set()

    def issue(
        self,
        intent: PaymentIntent,
        verdict: AuthorizationDecision,
        *,
        policy_version: str,
        now: datetime | None = None,
    ) -> ExecutionAuthorization:
        if verdict.intent_id != intent.id:
            raise AuthorizationError("authorization intent mismatch")
        if verdict.decision != Decision.ALLOW:
            raise AuthorizationError("only ALLOW verdicts can be authorized")

        issued_at = now or datetime.now(timezone.utc)
        return ExecutionAuthorization(
            id=uuid4(),
            intent_id=intent.id,
            correlation_id=verdict.correlation_id,
            policy_version=policy_version,
            issued_at=issued_at,
            expires_at=issued_at + self._ttl,
            nonce=uuid4().hex,
        )

    def consume(
        self,
        authorization: ExecutionAuthorization,
        intent: PaymentIntent,
        *,
        now: datetime | None = None,
    ) -> None:
        if authorization.intent_id != intent.id:
            raise AuthorizationError("authorization intent mismatch")
        if authorization.id in self._consumed:
            raise AuthorizationError("authorization already consumed")
        if not authorization.is_valid_at(now):
            raise AuthorizationError("authorization expired or not yet valid")
        self._consumed.add(authorization.id)
