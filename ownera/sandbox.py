"""Deterministic financial sandbox for OWNERA development."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from .audit import AuditEvent
from .domain import Decision, Money, PaymentIntent
from .firewall import TransactionFirewall


@dataclass(frozen=True)
class SimulatedPayment:
    intent: PaymentIntent
    decision: Decision
    committed: bool


class SandboxTreasury:
    def __init__(self, firewall: TransactionFirewall, balance: Decimal = Decimal("0"), currency: str = "EUR") -> None:
        self._firewall = firewall
        self.balance = balance
        self.currency = currency

    def propose_payment(
        self,
        amount: Decimal,
        destination: str,
        purpose: str,
        *,
        idempotency_key: str | None = None,
    ) -> SimulatedPayment:
        intent = PaymentIntent(
            amount=Money(amount, self.currency),
            destination=destination,
            purpose=purpose,
            idempotency_key=idempotency_key or f"sandbox:{destination}:{amount}:{purpose}",
        )
        verdict = self._firewall.evaluate(intent)

        if verdict.decision != Decision.ALLOW:
            self._firewall.audit.append(AuditEvent(
                event_type="execution.rejected",
                actor="sandbox",
                correlation_id=verdict.correlation_id,
                payload_hash=f"intent:{intent.id}",
            ))
            return SimulatedPayment(intent, verdict.decision, False)

        if amount > self.balance:
            self._firewall.audit.append(AuditEvent(
                event_type="execution.rejected",
                actor="sandbox",
                correlation_id=verdict.correlation_id,
                payload_hash=f"intent:{intent.id}",
            ))
            return SimulatedPayment(intent, Decision.REVIEW, False)

        self.balance -= amount
        self._firewall.ledger.append(intent)
        self._firewall.audit.append(AuditEvent(
            event_type="execution.committed",
            actor="sandbox",
            correlation_id=verdict.correlation_id,
            payload_hash=f"intent:{intent.id}",
        ))
        return SimulatedPayment(intent, Decision.ALLOW, True)
