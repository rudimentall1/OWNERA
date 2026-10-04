from decimal import Decimal

from ownera.domain import Decision
from ownera.investment import InvestmentPolicy, PortfolioSnapshot, TradeProposal, TradeSide
from ownera.investment_sandbox import InvestmentSandbox


def _sandbox() -> InvestmentSandbox:
    return InvestmentSandbox(
        PortfolioSnapshot("USD", Decimal("7000"), ()),
        InvestmentPolicy(
            max_single_trade=Decimal("500"),
            reserve_floor=Decimal("3000"),
            max_position_percent=Decimal("40"),
            max_daily_turnover=Decimal("1000"),
            currency="USD",
        ),
    )


def test_autonomous_trade_crosses_authority_updates_portfolio_and_produces_evidence() -> None:
    result = _sandbox().propose_trade(
        TradeProposal("BTC", TradeSide.BUY, Decimal("0.005"), Decimal("60000"), "USD")
    )
    assert result.decision is Decision.ALLOW
    assert result.committed is True
    assert result.authorization is not None
    assert result.financial_action is not None
    assert result.receipt is not None
    assert result.evidence is not None
    assert result.evidence.verify_integrity()
    assert result.financial_action.metadata["quantity_exact"] == "0.005"
    assert result.financial_action.metadata["price_exact"] == "60000"
    assert result.financial_action.action_type == "investment.buy"
    assert result.portfolio_after.cash == Decimal("6700")
    assert result.portfolio_after.position_value("BTC") == Decimal("300")
    assert result.evidence.evidence_sha256 == result.audit.all()[-1].payload_hash if result.audit.all() else False


def test_denied_trade_never_changes_portfolio_or_gets_authority() -> None:
    sandbox = _sandbox()
    result = sandbox.propose_trade(
        TradeProposal("BTC", TradeSide.BUY, Decimal("0.02"), Decimal("60000"), "USD")
    )
    assert result.decision is Decision.DENY
    assert result.committed is False
    assert result.authorization is None
    assert result.evidence is None
    assert sandbox.portfolio.cash == Decimal("7000")
