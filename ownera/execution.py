"""Autonomous obligation execution orchestration for the sandbox.

Scheduling proposes what is due. This service is the only orchestration layer
that may turn a due obligation into an execution attempt, and execution still
has to cross the treasury firewall and authority boundary.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from .domain import Decision
from .obligations import ObligationBook
from .sandbox import SandboxTreasury, SimulatedPayment


@dataclass(frozen=True)
class ObligationExecution:
    """Result of one due-obligation execution attempt."""

    payment: SimulatedPayment
    paid: bool


class ObligationExecutionService:
    """Runs due obligations through the complete deterministic execution path."""

    def __init__(self, book: ObligationBook, treasury: SandboxTreasury) -> None:
        self._book = book
        self._treasury = treasury

    def execute_due(self, day: date) -> tuple[ObligationExecution, ...]:
        results: list[ObligationExecution] = []
        for obligation in self._book.due_on(day):
            intent = self._book.to_payment_intent(obligation)
            payment = self._treasury.execute_intent(intent)
            paid = payment.committed and payment.decision == Decision.ALLOW
            if paid:
                self._book.mark_paid(obligation)
            results.append(ObligationExecution(payment=payment, paid=paid))
        return tuple(results)

    def balance(self) -> Decimal:
        return self._treasury.balance
