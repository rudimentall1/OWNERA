"""Final deterministic execution gate.

The firewall deliberately accepts only structured, already-created intents and
never talks to an LLM. Provider-specific execution belongs outside this layer.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID, uuid4

from .audit import AuditEvent, AuditLog
from .domain import Decision, PaymentIntent, RiskLevel
from .security import RiskEngine, SpendingPolicy, authorize


@dataclass(frozen=True)
class FirewallConfig:
    policy: SpendingPolicy
    autonomous_max_risk: RiskLevel = RiskLevel.LOW


@dataclass(frozen=True)
class AuthorizationDecision:
    intent_id: UUID
    decision: Decision
    reasons: tuple[str, ...]
    correlation_id: UUID


class TransactionFirewall:
    """Combines independent deterministic controls into one execution verdict."""

    def __init__(self, config: FirewallConfig, audit: AuditLog | None = None) -> None:
        self._config = config
        self._risk = RiskEngine()
        self._audit = audit or AuditLog()

    def evaluate(self, intent: PaymentIntent) -> AuthorizationDecision:
        correlation_id = uuid4()
        policy = self._config.policy.evaluate(intent)
        risk = self._risk.evaluate(intent)
        decision = authorize(policy, risk)

        reasons = tuple((*policy.reasons, *risk.reasons))
        self._audit.append(
            AuditEvent(
                event_type="authorization.evaluated",
                actor="firewall",
                correlation_id=correlation_id,
                payload_hash=f"intent:{intent.id}",
                policy_version=policy.policy_version,
            )
        )
        return AuthorizationDecision(intent.id, decision, reasons, correlation_id)

    @property
    def audit(self) -> AuditLog:
        return self._audit
