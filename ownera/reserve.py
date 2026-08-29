"""Sovereign Reserve capability boundary."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


class ReserveAccessError(PermissionError):
    """Raised when an agent attempts an operation outside reserve authority."""


@dataclass
class SovereignReserve:
    """Conceptual reserve interface.

    The foundation layer intentionally exposes deposit only to the agent.
    Withdrawal and configuration authority belongs to an owner-controlled
    mechanism that is outside this class.
    """

    balance: Decimal = Decimal("0")

    def agent_deposit(self, amount: Decimal) -> None:
        if amount <= 0:
            raise ValueError("deposit amount must be positive")
        self.balance += amount

    def agent_withdraw(self, amount: Decimal) -> None:
        raise ReserveAccessError("agent withdrawal is permanently prohibited")

    def agent_transfer(self, amount: Decimal, destination: str) -> None:
        raise ReserveAccessError("agent transfer from reserve is permanently prohibited")

    def agent_reconfigure(self, *_args: object, **_kwargs: object) -> None:
        raise ReserveAccessError("agent reconfiguration of reserve is prohibited")
