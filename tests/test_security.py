from decimal import Decimal

import pytest

from ownera.domain import Decision, Money, PaymentIntent, RiskLevel
from ownera.reserve import ReserveAccessError, SovereignReserve
from ownera.security import RiskEngine, SpendingPolicy, authorize


def intent(amount: str, destination: str = "alice") -> PaymentIntent:
    return PaymentIntent(
        amount=Money(Decimal(amount), "EUR"),
        destination=destination,
        purpose="test",
        idempotency_key=f"test-{amount}-{destination}",
    )


def test_policy_allows_valid_payment() -> None:
    result = SpendingPolicy(Decimal("1000"), "EUR").evaluate(intent("50"))
    assert result.decision == Decision.ALLOW


def test_policy_reviews_large_payment() -> None:
    result = SpendingPolicy(Decimal("1000"), "EUR").evaluate(intent("1001"))
    assert result.decision == Decision.REVIEW


def test_risk_flags_large_transfer() -> None:
    result = RiskEngine().evaluate(intent("10000"))
    assert result.level == RiskLevel.HIGH


def test_authorization_is_conservative() -> None:
    policy = SpendingPolicy(Decimal("1000"), "EUR").evaluate(intent("50"))
    risk = RiskEngine().evaluate(intent("50"))
    assert authorize(policy, risk) == Decision.ALLOW


def test_reserve_only_accepts_agent_deposits() -> None:
    reserve = SovereignReserve()
    reserve.agent_deposit(Decimal("100"))
    assert reserve.balance == Decimal("100")

    with pytest.raises(ReserveAccessError):
        reserve.agent_withdraw(Decimal("1"))

    with pytest.raises(ReserveAccessError):
        reserve.agent_transfer(Decimal("1"), "attacker")

    with pytest.raises(ReserveAccessError):
        reserve.agent_reconfigure()
