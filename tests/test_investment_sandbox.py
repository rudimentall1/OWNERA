from decimal import Decimal

from ownera.domain import Decision
from ownera.investment import InvestmentPolicy, PortfolioSnapshot, TradeProposal, TradeSide
from ownera.investment_sandbox import InvestmentSandbox


def test_autonomous_trade_crosses_authority_and_updates_portfolio() -> None:
    sandbox = InvestmentSandbox(
        PortfolioSnapshot("USD", Decimal("7000"), ()),
        InvestmentPolicy(
            max_single_trade=Decimal("500"),
            reserve_floor=Decimal("3000"),
            max_position_percent=Decimal("40"),
            max_daily_turnover=Decimal("1000"),
            currency="USD",
        ),
    )

    result = sandbox.propose_trade(
        TradeProposal("BTC", TradeSide.BUY, Decimal("0.005"), Decimal("60000"), "USD")
    )

    assert result.decision is Decision.ALLOW
    assert result.committed is True
    assert result.authorization is not None
    assert result.financial_action is not None
    assert result.financial_action.action_type == "investment.buy"
    assert sandbox.portfolio.cash == Decimal("6700")
    assert sandbox.portfolio.position_value("BTC") == Decimal("300")


def test_denied_trade_never_changes_portfolio() -> None:
    sandbox = InvestmentSandbox(
        PortfolioSnapshot("USD", Decimal("7000"), ()),
        InvestmentPolicy(
            max_single_trade=Decimal("500"),
            reserve_floor=Decimal("3000"),
            max_position_percent=Decimal("40"),
            max_daily_turnover=Decimal("1000"),
            currency="USD",
        ),
    )

    result = sandbox.propose_trade(
        TradeProposal("BTC", TradeSide.BUY, Decimal("0.02"), Decimal("60000"), "USD")
    )

    assert result.decision is Decision.DENY
    assert result.committed is False
    assert result.authorization is None
    assert sandbox.portfolio.cash == Decimal("7000")
