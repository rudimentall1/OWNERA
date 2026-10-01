from datetime import date
from decimal import Decimal

import pytest

from ownera.obligations import (
    ObligationBook,
    Recurrence,
    RecurringObligation,
    due_date,
)


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
    schedule = make_schedule(
        first_due_date=date(2026, 10, 1),
        recurrence=Recurrence.WEEKLY,
    )
    assert due_date(schedule, 2) == date(2026, 10, 15)


def test_book_returns_only_obligations_due_on_requested_day() -> None:
    book = ObligationBook()
    book.register(make_schedule())

    due = book.due_on(date(2026, 2, 28))

    assert len(due) == 1
    assert due[0].name == "Rent"
    assert due[0].status.value == "DUE"


def test_book_does_not_execute_or_authorize_obligation() -> None:
    book = ObligationBook()
    book.register(make_schedule())

    due = book.due_on(date(2026, 1, 31))

    assert len(due) == 1
    assert not hasattr(due[0], "authorization")
    assert due[0].status.value == "DUE"


def test_schedule_rejects_invalid_end_date() -> None:
    with pytest.raises(ValueError, match="end date"):
        make_schedule(end_date=date(2025, 12, 31))
