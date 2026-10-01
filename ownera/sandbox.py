"""Deterministic financial sandbox for OWNERA development."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from .audit import AuditEvent
from .authority import AuthorityPort, LocalAuthorityAdapter
from .authorization import AuthorizationError, ExecutionAuthorization
from .domain import Decision, Money, PaymentIntent
from .firewall import TransactionFirewall
from .receipt import ExecutionReceipt


@dataclass(frozen=True)
class SimulatedPayment:
    intent: PaymentIntent
    decision: Decision
    committed: bool
    authorization: ExecutionAuthorization | None = None
    receipt: ExecutionReceipt | None = None


class SandboxTreasury:
    def __init__(
        self,
        firewall: TransactionFirewall,
        balance: Decimal = Decimal("0"),
        currency: str = "EUR",
        authority: AuthorityPort | None = None,
    ) -> None:
        self._firewall = firewall
        self._authority = authority or LocalAuthorityAdapter.create()
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
        return self.execute_intent(intent)

    def execute_intent(self, intent: PaymentIntent) -> SimulatedPayment:
        """Evaluate and execute an already-constructed intent through the full boundary."""
        if intent.amount.currency != self.currency:
            return SimulatedPayment(intent, Decision.DENY, False)

        verdict = self._firewall.evaluate(intent)

        if verdict.decision != Decision.ALLOW:
            self._firewall.audit.append(
                AuditEvent(
                    event_type="execution.rejected",
                    actor="sandbox",
                    correlation_id=verdict.correlation_id,
                    payload_hash=f"intent:{intent.id}",
                )
            )
            return SimulatedPayment(intent, verdict.decision, False)

        if intent.amount.amount > self.balance:
            self._firewall.audit.append(
                AuditEvent(
                    event_type="execution.rejected",
                    actor="sandbox",
                    correlation_id=verdict.correlation_id,
                    payload_hash=f"intent:{intent.id}",
                )
            )
            return SimulatedPayment(intent, Decision.REVIEW, False)

        authorization = self._authority.issue(
            intent,
            verdict,
            policy_version=self._firewall.policy_version,
        )
        try:
            self._authority.consume(authorization, intent)
        except AuthorizationError:
            self._firewall.audit.append(
                AuditEvent(
                    event_type="execution.rejected",
                    actor="sandbox",
                    correlation_id=verdict.correlation_id,
                    payload_hash=f"intent:{intent.id}",
                )
            )
            return SimulatedPayment(
                intent,
                Decision.DENY,
                False,
                authorization=authorization,
            )

        self.balance -= intent.amount.amount
        self._firewall.ledger.append(intent)
        receipt = ExecutionReceipt.committed(
            authorization,
            amount=intent.amount.amount,
            currency=intent.amount.currency,
            destination=intent.destination,
        )
        self._firewall.audit.append(
            AuditEvent(
                event_type="execution.committed",
                actor="sandbox",
                correlation_id=verdict.correlation_id,
                payload_hash=f"intent:{intent.id}",
            )
        )
        return SimulatedPayment(
            intent,
            Decision.ALLOW,
            True,
            authorization=authorization,
            receipt=receipt,
        )
