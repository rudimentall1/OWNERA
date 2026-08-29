"""Deterministic financial sandbox for OWNERA development.

No network access, real accounts, private keys, or real-money execution occur
in this module. It exists to exercise the authorization architecture safely.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

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

    def propose_payment(self, amount: Decimal, destination: str, purpose: str) -> SimulatedPayment:
        intent = PaymentIntent(
            amount=Money(amount, self.currency),
            destination=destination,
            purpose=purpose,
            idempotency_key=f"sandbox:{destination}:{amount}:{purpose}",
        )
        verdict = self._firewall.evaluate(intent)
        committed = verdict.decision == Decision.ALLOW
        if committed:
            if amount > self.balance:
                return SimulatedPayment(intent, Decision.REVIEW, False)
            self.balance -= amount
        return SimulatedPayment(intent, verdict.decision, committed)
