from decimal import Decimal

from ownera.investment import (
    InvestmentDecision,
    InvestmentFirewall,
    InvestmentPolicy,
    PortfolioSnapshot,
    Position,
    TradeProposal,
    TradeSide,
)


def portfolio() -> PortfolioSnapshot:
    return PortfolioSnapshot(
        currency="USD",
        cash=Decimal("7000"),
        positions=(Position("BTC", Decimal("0.05"), Decimal("60000")),),
    )


def policy() -> InvestmentPolicy:
    return InvestmentPolicy(
        max_single_trade=Decimal("500"),
        reserve_floor=Decimal("3000"),
        max_position_percent=Decimal("40"),
        max_daily_turnover=Decimal("1000"),
        currency="USD",
    )


def test_buy_is_allowed_when_all_constraints_hold() -> None:
    result = InvestmentFirewall().evaluate(
        portfolio(),
        TradeProposal("BTC", TradeSide.BUY, Decimal("0.005"), Decimal("60000"), "USD"),
        policy(),
    )

    assert result.decision is InvestmentDecision.ALLOW
    assert result.reason == "policy_satisfied"


def test_buy_cannot_break_reserve_floor() -> None:
    result = InvestmentFirewall().evaluate(
        portfolio(),
        TradeProposal("ETH", TradeSide.BUY, Decimal("0.02"), Decimal("30000"), "USD"),
        InvestmentPolicy(
            max_single_trade=Decimal("5000"),
            reserve_floor=Decimal("3000"),
            max_position_percent=Decimal("40"),
            max_daily_turnover=Decimal("5000"),
            currency="USD",
        ),
    )

    assert result.decision is InvestmentDecision.DENY
    assert result.reason == "reserve_floor"


def test_buy_cannot_exceed_single_trade_limit() -> None:
    result = InvestmentFirewall().evaluate(
        portfolio(),
        TradeProposal("BTC", TradeSide.BUY, Decimal("0.01"), Decimal("60000"), "USD"),
        policy(),
    )

    assert result.decision is InvestmentDecision.DENY
    assert result.reason == "single_trade_limit"


def test_buy_cannot_exceed_concentration_limit() -> None:
    result = InvestmentFirewall().evaluate(
        portfolio(),
        TradeProposal("BTC", TradeSide.BUY, Decimal("0.005"), Decimal("60000"), "USD"),
        InvestmentPolicy(
            max_single_trade=Decimal("500"),
            reserve_floor=Decimal("3000"),
            max_position_percent=Decimal("20"),
            max_daily_turnover=Decimal("1000"),
            currency="USD",
        ),
    )

    assert result.decision is InvestmentDecision.DENY
    assert result.reason == "position_concentration"


def test_sell_cannot_exceed_held_position() -> None:
    result = InvestmentFirewall().evaluate(
        portfolio(),
        TradeProposal("BTC", TradeSide.SELL, Decimal("0.1"), Decimal("60000"), "USD"),
        InvestmentPolicy(
            max_single_trade=Decimal("10000"),
            reserve_floor=Decimal("3000"),
            max_position_percent=Decimal("40"),
            max_daily_turnover=Decimal("10000"),
            currency="USD",
        ),
    )

    assert result.decision is InvestmentDecision.DENY
    assert result.reason == "insufficient_position"


def test_daily_turnover_is_enforced() -> None:
    result = InvestmentFirewall().evaluate(
        portfolio(),
        TradeProposal("ETH", TradeSide.BUY, Decimal("0.01"), Decimal("40000"), "USD"),
        policy(),
        daily_turnover=Decimal("700"),
    )

    assert result.decision is InvestmentDecision.DENY
    assert result.reason == "daily_turnover_limit"


def test_currency_mismatch_fails_closed() -> None:
    result = InvestmentFirewall().evaluate(
        portfolio(),
        TradeProposal("BTC", TradeSide.BUY, Decimal("0.005"), Decimal("60000"), "EUR"),
        policy(),
    )

    assert result.decision is InvestmentDecision.DENY
    assert result.reason == "currency_mismatch"
