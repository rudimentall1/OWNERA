"""Deterministic security gates for OWNERA.

This module intentionally contains no model calls and no key material.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from .domain import Decision, PaymentIntent, PolicyResult, RiskLevel, RiskResult


@dataclass(frozen=True)
class SpendingPolicy:
    max_single_payment: Decimal
    currency: str
    allowed_destinations: frozenset[str] = frozenset()

    def evaluate(self, intent: PaymentIntent) -> PolicyResult:
        if intent.amount.currency != self.currency:
            return PolicyResult(Decision.REVIEW, ("currency_not_supported",))

        if intent.amount.amount <= 0:
            return PolicyResult(Decision.DENY, ("amount_must_be_positive",))

        if intent.amount.amount > self.max_single_payment:
            return PolicyResult(Decision.REVIEW, ("single_payment_limit_exceeded",))

        if self.allowed_destinations and intent.destination not in self.allowed_destinations:
            return PolicyResult(Decision.REVIEW, ("destination_not_allowlisted",))

        return PolicyResult(Decision.ALLOW, ("policy_satisfied",))


class RiskEngine:
    """Minimal deterministic risk engine used by the foundation layer."""

    def evaluate(self, intent: PaymentIntent) -> RiskResult:
        if not intent.destination.strip():
            return RiskResult(RiskLevel.CRITICAL, Decimal("1.0"), ("missing_destination",))

        if intent.amount.amount >= Decimal("10000"):
            return RiskResult(RiskLevel.HIGH, Decimal("0.75"), ("large_value_transfer",))

        return RiskResult(RiskLevel.LOW, Decimal("0.10"), ("baseline_risk",))


def authorize(policy: PolicyResult, risk: RiskResult) -> Decision:
    """Combine independent policy and risk results into a conservative decision."""
    if policy.decision == Decision.DENY or risk.level == RiskLevel.CRITICAL:
        return Decision.DENY
    if policy.decision == Decision.REVIEW or risk.level in {RiskLevel.HIGH, RiskLevel.MEDIUM}:
        return Decision.REVIEW
    return Decision.ALLOW
