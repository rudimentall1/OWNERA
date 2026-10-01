from datetime import date
from decimal import Decimal

from ownera.execution import ObligationExecutionService
from ownera.firewall import FirewallConfig, TransactionFirewall
from ownera.obligations import ObligationBook, Recurrence, RecurringObligation
from ownera.sandbox import SandboxTreasury
from ownera.security import SpendingPolicy


def make_service(balance: Decimal = Decimal("2000")) -> tuple[ObligationBook, ObligationExecutionService]:
    book = ObligationBook()
    book.register(
        RecurringObligation(
            name="Rent",
            amount=Decimal("1200"),
            currency="EUR",
            destination="landlord",
            first_due_date=date(2026, 10, 1),
            recurrence=Recurrence.MONTHLY,
        )
    )
    firewall = TransactionFirewall(
        FirewallConfig(
            policy=SpendingPolicy(max_single_payment=Decimal("2000"), currency="EUR")
        )
    )
    treasury = SandboxTreasury(firewall, balance=balance)
    return book, ObligationExecutionService(book, treasury)


def test_due_obligation_executes_end_to_end_and_becomes_paid() -> None:
    book, service = make_service()

    results = service.execute_due(date(2026, 10, 1))

    assert len(results) == 1
    result = results[0]
    assert result.paid is True
    assert result.payment.committed is True
    assert result.payment.authorization is not None
    assert result.payment.receipt is not None
    assert service.balance() == Decimal("800")
    assert book.due_on(date(2026, 10, 1)) == ()


def test_paid_obligation_is_not_executed_again() -> None:
    _, service = make_service()

    first = service.execute_due(date(2026, 10, 1))
    second = service.execute_due(date(2026, 10, 1))

    assert first[0].paid is True
    assert second == ()
    assert service.balance() == Decimal("800")


def test_insufficient_balance_does_not_authorize_or_mark_paid() -> None:
    book, service = make_service(balance=Decimal("1000"))

    results = service.execute_due(date(2026, 10, 1))

    assert len(results) == 1
    result = results[0]
    assert result.paid is False
    assert result.payment.committed is False
    assert result.payment.authorization is None
    assert result.payment.receipt is None
    assert book.due_on(date(2026, 10, 1))
    assert service.balance() == Decimal("1000")
