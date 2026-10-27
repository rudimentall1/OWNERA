from datetime import datetime, timezone
from decimal import Decimal

import pytest

from ownera.agent import MarketSnapshot
from ownera.domain import Decision
from ownera.investment import InvestmentPolicy, PortfolioSnapshot, TradeSide
from ownera.investment_sandbox import InvestmentSandbox
from ownera.strategy_adapter import StrategyAdapterError, ValidatedStrategyAdapter
from ownera.treasury_cycle import AutonomousTreasuryCycle


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



def test_external_strategy_flows_through_treasury_authority_and_evidence():
    adapter = _adapter(_payload())
    sandbox = InvestmentSandbox(
        _portfolio(),
        InvestmentPolicy(
            max_single_trade=Decimal("500"),
            reserve_floor=Decimal("3000"),
            max_position_percent=Decimal("40"),
            max_daily_turnover=Decimal("1000"),
            currency="USD",
        ),
    )
    cycle = AutonomousTreasuryCycle(adapter, sandbox)

    result = cycle.run_once(
        _market(),
        now=datetime(2026, 10, 27, 0, 1, tzinfo=timezone.utc),
    )

    assert result.proposal_created is True
    assert result.trade is not None
    assert result.trade.decision is Decision.ALLOW
    assert result.trade.committed is True
    assert result.trade.evidence is not None
    assert result.trade.evidence.verify_integrity()
    assert result.outcome is not None
    assert result.outcome.status == "EXECUTED"
    assert result.outcome.intent_id == result.trade.proposal.id
    assert result.outcome.authorization_id == result.trade.authorization.id
    assert sandbox.portfolio.cash == Decimal("9940.000")
