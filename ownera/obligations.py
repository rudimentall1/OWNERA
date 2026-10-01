"""Deterministic obligation scheduling for the OWNERA sandbox.

Recurring obligations are financial commitments, not execution permissions.
Scheduling may create a PaymentIntent candidate; it never authorizes or executes
money movement.
"""

from __future__ import annotations

from calendar import monthrange
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from enum import Enum
from uuid import UUID, uuid4, uuid5

from .domain import Money, PaymentIntent
from .finance import Obligation, ObligationStatus


class Recurrence(str, Enum):
    DAILY = "DAILY"
    WEEKLY = "WEEKLY"
    MONTHLY = "MONTHLY"


@dataclass(frozen=True)
class RecurringObligation:
    """A reusable obligation schedule with deterministic next-due calculation."""

    name: str
    amount: Decimal
    currency: str
    destination: str
    first_due_date: date
    recurrence: Recurrence
    id: UUID = field(default_factory=uuid4)
    end_date: date | None = None

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("recurring obligation name is required")
        if self.amount <= 0:
            raise ValueError("recurring obligation amount must be positive")
        if not self.currency.strip():
            raise ValueError("recurring obligation currency is required")
        if not self.destination.strip():
            raise ValueError("recurring obligation destination is required")
        if self.end_date is not None and self.end_date < self.first_due_date:
            raise ValueError("end date cannot precede first due date")


def _add_months(value: date, months: int) -> date:
    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    day = min(value.day, monthrange(year, month)[1])
    return date(year, month, day)


def _advance(value: date, recurrence: Recurrence) -> date:
    if recurrence == Recurrence.DAILY:
        return value + timedelta(days=1)
    if recurrence == Recurrence.WEEKLY:
        return value + timedelta(weeks=1)
    return _add_months(value, 1)


def due_date(schedule: RecurringObligation, occurrence: int) -> date:
    """Return the deterministic date for a zero-based occurrence number."""
    if occurrence < 0:
        raise ValueError("occurrence cannot be negative")
    if schedule.recurrence == Recurrence.MONTHLY:
        return _add_months(schedule.first_due_date, occurrence)
    if schedule.recurrence == Recurrence.WEEKLY:
        return schedule.first_due_date + timedelta(weeks=occurrence)
    return schedule.first_due_date + timedelta(days=occurrence)


@dataclass
class ObligationBook:
    """In-memory schedule registry for the financial sandbox."""

    _schedules: dict[UUID, RecurringObligation] = field(default_factory=dict)

    def register(self, schedule: RecurringObligation) -> UUID:
        if schedule.id in self._schedules:
            raise ValueError("duplicate recurring obligation")
        self._schedules[schedule.id] = schedule
        return schedule.id

    def get(self, schedule_id: UUID) -> RecurringObligation:
        return self._schedules[schedule_id]

    def due_on(self, day: date) -> tuple[Obligation, ...]:
        obligations: list[Obligation] = []
        for schedule in self._schedules.values():
            if day < schedule.first_due_date:
                continue
            if schedule.end_date is not None and day > schedule.end_date:
                continue

            occurrence = 0
            current = schedule.first_due_date
            while current < day:
                current = _advance(current, schedule.recurrence)
                occurrence += 1
            if current != day:
                continue

            occurrence_id = uuid5(schedule.id, day.isoformat())
            obligations.append(
                Obligation(
                    name=schedule.name,
                    amount=schedule.amount,
                    currency=schedule.currency,
                    due_date=day,
                    destination=schedule.destination,
                    status=ObligationStatus.DUE,
                    id=occurrence_id,
                )
            )
        return tuple(obligations)

    def all(self) -> tuple[RecurringObligation, ...]:
        return tuple(self._schedules.values())

    @staticmethod
    def to_payment_intent(obligation: Obligation) -> PaymentIntent:
        """Convert a due obligation into an intent candidate, never an authorization."""
        if obligation.status != ObligationStatus.DUE:
            raise ValueError("only due obligations can become payment intents")
        return PaymentIntent(
            amount=Money(obligation.amount, obligation.currency),
            destination=obligation.destination,
            purpose=f"obligation:{obligation.name}",
            obligation_id=obligation.id,
            idempotency_key=f"obligation:{obligation.id}:{obligation.due_date.isoformat()}",
        )
