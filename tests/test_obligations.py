from datetime import date
from decimal import Decimal

import pytest

from ownera.domain import PaymentIntent
from ownera.finance import Obligation, ObligationStatus
from ownera.obligations import ObligationBook, Recurrence, RecurringObligation, due_date


def make_schedule(**overrides: object) -> RecurringObligation:
    values: dict[str, object] = {
        "name": "Rent",
        "amount": Decimal("1200"),
        "currency": "EUR",
        "destination": "landlord",
        "first_due_date": date(2026, 1, 31),
        "recurrence": Recurrence.MONTHLY,
    }
    values.update(overrides)
    return RecurringObligation(**values)


def test_monthly_schedule_clamps_end_of_month() -> None:
    schedule = make_schedule()
    assert due_date(schedule, 1) == date(2026, 2, 28)
    assert due_date(schedule, 2) == date(2026, 3, 31)


def test_weekly_schedule_is_deterministic() -> None:
    schedule = make_schedule(first_due_date=date(2026, 10, 1), recurrence=Recurrence.WEEKLY)
    assert due_date(schedule, 2) == date(2026, 10, 15)


def test_book_returns_only_obligations_due_on_requested_day() -> None:
    book = ObligationBook()
    book.register(make_schedule())
    due = book.due_on(date(2026, 2, 28))
    assert len(due) == 1
    assert due[0].name == "Rent"
    assert due[0].status == ObligationStatus.DUE


def test_book_does_not_execute_or_authorize_obligation() -> None:
    book = ObligationBook()
    book.register(make_schedule())
    due = book.due_on(date(2026, 1, 31))
    assert len(due) == 1
    assert due[0].status == ObligationStatus.DUE


def test_due_obligation_becomes_deterministic_payment_intent_candidate() -> None:
    book = ObligationBook()
    book.register(make_schedule())
    obligation = book.due_on(date(2026, 1, 31))[0]

    intent = book.to_payment_intent(obligation)

    assert isinstance(intent, PaymentIntent)
    assert intent.obligation_id == obligation.id
    assert intent.amount.amount == Decimal("1200")
    assert intent.amount.currency == "EUR"
    assert intent.destination == "landlord"
    assert intent.idempotency_key == f"obligation:{obligation.id}:2026-01-31"


def test_non_due_obligation_cannot_become_payment_intent() -> None:
    obligation = Obligation(
        name="Rent",
        amount=Decimal("1200"),
        currency="EUR",
        due_date=date(2026, 1, 31),
        destination="landlord",
    )
    with pytest.raises(ValueError, match="only due"):
        ObligationBook.to_payment_intent(obligation)
