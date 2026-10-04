"""Authority boundary for OWNERA financial execution."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from .authorization import AuthorizationIssuer, ExecutionAuthorization, FinancialIntent
from .domain import Decision
from .firewall import AuthorizationDecision


class AuthorityPort(Protocol):
    @property
    def agent_id(self) -> str:
        ...

    def issue(
        self,
        intent: FinancialIntent,
        verdict: AuthorizationDecision,
        *,
        policy_version: str,
        now: datetime | None = None,
    ) -> ExecutionAuthorization:
        ...

    def consume(
        self,
        authorization: ExecutionAuthorization,
        intent: FinancialIntent,
        *,
        now: datetime | None = None,
    ) -> None:
        ...


@dataclass
class LocalAuthorityAdapter:
    issuer: AuthorizationIssuer
    agent_id: str = "ownera-sandbox"

    @classmethod
    def create(
        cls,
        ttl_seconds: int = 60,
        agent_id: str = "ownera-sandbox",
    ) -> LocalAuthorityAdapter:
        return cls(AuthorizationIssuer(ttl_seconds=ttl_seconds), agent_id=agent_id)

    def issue(
        self,
        intent: FinancialIntent,
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
        intent: FinancialIntent,
        *,
        now: datetime | None = None,
    ) -> None:
        self.issuer.consume(authorization, intent, now=now)


def requires_execution_authority(verdict: AuthorizationDecision) -> bool:
    return verdict.decision == Decision.ALLOW
