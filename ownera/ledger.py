"""Deterministic sandbox ledger for financial execution state.

The ledger is intentionally provider-agnostic. It gives policy evaluation the
minimum state needed for replay protection and rolling spend limits without
making the policy engine itself stateful.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import UUID

from .domain import Money, PaymentIntent


@dataclass(frozen=True)
class LedgerEntry:
    intent_id: UUID
    idempotency_key: str
    amount: Money
    destination: str
    committed_at: datetime


class SandboxLedger:
    """Append-only execution ledger used by the financial sandbox."""

    def __init__(self) -> None:
        self._entries: list[LedgerEntry] = []

    def contains_idempotency_key(self, key: str) -> bool:
        return bool(key) and any(entry.idempotency_key == key for entry in self._entries)

    def total_for_date(self, day: date, currency: str) -> Decimal:
        return sum(
            (
                entry.amount.amount
                for entry in self._entries
                if entry.committed_at.astimezone(timezone.utc).date() == day
                and entry.amount.currency == currency
            ),
            Decimal("0"),
        )

    def append(self, intent: PaymentIntent) -> LedgerEntry:
        if self.contains_idempotency_key(intent.idempotency_key):
            raise ValueError("duplicate idempotency key")

        entry = LedgerEntry(
            intent_id=intent.id,
            idempotency_key=intent.idempotency_key,
            amount=intent.amount,
            destination=intent.destination,
            committed_at=datetime.now(timezone.utc),
        )
        self._entries.append(entry)
        return entry

    def all(self) -> tuple[LedgerEntry, ...]:
        return tuple(self._entries)
