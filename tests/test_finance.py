from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest

from ownera.finance import (
    Account,
    AccountKind,
    Asset,
    AssetKind,
    Balance,
    Liability,
    LiabilityKind,
    Obligation,
    ObligationStatus,
    Position,
)


def test_financial_entities_are_provider_neutral() -> None:
    asset = Asset("EUR", AssetKind.CASH)
    account = Account("Operating", AccountKind.CASH, "EUR")
    balance = Balance(account.id, asset.id, Decimal("1250"))

    assert balance.account_id == account.id
    assert balance.asset_id == asset.id
    assert balance.quantity == Decimal("1250")


def test_obligation_can_represent_a_future_payment() -> None:
    obligation = Obligation(
        name="Rent",
        amount=Decimal("900"),
        currency="EUR",
        due_date=date(2026, 10, 5),
        destination="landlord",
    )

    assert obligation.status == ObligationStatus.SCHEDULED
    assert obligation.amount == Decimal("900")


def test_liability_and_position_are_distinct_financial_concepts() -> None:
    liability = Liability(
        name="Credit card",
        kind=LiabilityKind.CREDIT,
        amount=Decimal("400"),
        currency="EUR",
    )
    asset = Asset("BTC", AssetKind.CRYPTO, decimals=8)
    account = Account("Crypto", AccountKind.CRYPTO, "BTC")
    position = Position(
        account_id=account.id,
        asset_id=asset.id,
        quantity=Decimal("0.25"),
        average_cost=Decimal("50000"),
    )

    assert liability.amount == Decimal("400")
    assert position.quantity == Decimal("0.25")


@pytest.mark.parametrize(
    "factory",
    [
        lambda: Asset("", AssetKind.CASH),
        lambda: Account("", AccountKind.CASH, "EUR"),
        lambda: Balance(uuid4(), __import__("uuid").uuid4(), Decimal("-1")),
        lambda: Liability("Debt", LiabilityKind.DEBT, Decimal("-1"), "EUR"),
        lambda: Obligation("Bill", Decimal("0"), "EUR", date(2026, 10, 5), "vendor"),
        lambda: Position(__import__("uuid").uuid4(), __import__("uuid").uuid4(), Decimal("-1")),
    ],
)
def test_financial_entities_reject_invalid_values(factory) -> None:
    with pytest.raises(ValueError):
        factory()
