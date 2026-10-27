from decimal import Decimal

import pytest

from ownera.agent import MarketSnapshot
from ownera.investment import PortfolioSnapshot, TradeSide
from ownera.strategy_adapter import StrategyAdapterError, ValidatedStrategyAdapter


class FakeProvider:
    def __init__(self, payload):
        self.payload = payload

    def propose(self, portfolio, market):
        return self.payload


def _adapter(payload):
    return ValidatedStrategyAdapter(
        FakeProvider(payload),
        allowed_assets={"BTC", "ETH"},
        currency="USD",
        provider_id="test-provider",
    )


def _portfolio():
    return PortfolioSnapshot("USD", Decimal("10000"))


def _market():
    from datetime import datetime, timezone

    return MarketSnapshot(
        {"BTC": Decimal("60000"), "ETH": Decimal("3000")},
        datetime(2026, 10, 27, tzinfo=timezone.utc),
    )


def _payload(**overrides):
    payload = {
        "asset": "BTC",
        "side": "BUY",
        "quantity": "0.001",
        "price": "60000",
        "currency": "USD",
        "rationale": "test proposal",
    }
    payload.update(overrides)
    return payload


def test_adapter_normalizes_valid_proposal_without_executing_it():
    proposal = _adapter(_payload()).propose(_portfolio(), _market())

    assert proposal is not None
    assert proposal.asset == "BTC"
    assert proposal.side is TradeSide.BUY
    assert proposal.quantity == Decimal("0.001")
    assert proposal.notional == Decimal("60.000")
    assert proposal.price == Decimal("60000")


def test_adapter_allows_provider_to_return_no_proposal():
    assert _adapter(None).propose(_portfolio(), _market()) is None


@pytest.mark.parametrize(
    ("override", "message"),
    [
        ({"asset": "SOL"}, "asset is not allowed"),
        ({"currency": "EUR"}, "currency does not match"),
        ({"price": "60001"}, "price does not match"),
        ({"quantity": 0.001}, "must not be a float"),
        ({"quantity": "NaN"}, "must be finite"),
        ({"quantity": "0"}, "quantity must be positive"),
        ({"side": "SHORT"}, "side must be BUY or SELL"),
        ({"unexpected": "execute_now"}, "unknown fields"),
    ],
)
def test_adapter_rejects_untrusted_or_invalid_proposals(override, message):
    with pytest.raises(StrategyAdapterError, match=message):
        _adapter(_payload(**override)).propose(_portfolio(), _market())


def test_adapter_rejects_incomplete_payload():
    payload = _payload()
    del payload["price"]

    with pytest.raises(StrategyAdapterError, match="missing required fields"):
        _adapter(payload).propose(_portfolio(), _market())


def test_adapter_rejects_portfolio_currency_mismatch():
    portfolio = PortfolioSnapshot("EUR", Decimal("10000"))

    with pytest.raises(StrategyAdapterError, match="portfolio currency"):
        _adapter(_payload()).propose(portfolio, _market())


def test_adapter_rejects_price_for_asset_not_in_market():
    payload = _payload(asset="ETH", price="60000")

    with pytest.raises(StrategyAdapterError, match="price does not match"):
        _adapter(payload).propose(_portfolio(), _market())
