"""Authority boundary for OWNERA financial execution.

OWNERA owns financial intent and treasury state. Authority is deliberately
behind a provider-neutral port so the production implementation can delegate
to Verigate instead of reimplementing its authority protocol.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from .authorization import AuthorizationIssuer, ExecutionAuthorization
from .domain import Decision, PaymentIntent
from .firewall import AuthorizationDecision


class AuthorityPort(Protocol):
    """Minimum authority contract required by the financial execution layer."""

    def issue(
        self,
        intent: PaymentIntent,
        verdict: AuthorizationDecision,
        *,
        policy_version: str,
        now: datetime | None = None,
    ) -> ExecutionAuthorization:
        ...

    def consume(
        self,
        authorization: ExecutionAuthorization,
        intent: PaymentIntent,
        *,
        now: datetime | None = None,
    ) -> None:
        ...


@dataclass
class LocalAuthorityAdapter:
    """Sandbox adapter used until OWNERA is connected to Verigate."""

    issuer: AuthorizationIssuer

    @classmethod
    def create(cls, ttl_seconds: int = 60) -> LocalAuthorityAdapter:
        return cls(AuthorizationIssuer(ttl_seconds=ttl_seconds))

    def issue(
        self,
        intent: PaymentIntent,
        verdict: AuthorizationDecision,
        *,
        policy_version: str,
        now: datetime | None = None,
    ) -> ExecutionAuthorization:
        return self.issuer.issue(
            intent,
            verdict,
            policy_version=policy_version,
            now=now,
        )

    def consume(
        self,
        authorization: ExecutionAuthorization,
        intent: PaymentIntent,
        *,
        now: datetime | None = None,
    ) -> None:
        self.issuer.consume(authorization, intent, now=now)


def requires_execution_authority(verdict: AuthorizationDecision) -> bool:
    """Only ALLOW can cross the execution authority boundary."""
    return verdict.decision == Decision.ALLOW
