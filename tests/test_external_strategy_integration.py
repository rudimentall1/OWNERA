import sys
from datetime import datetime, timezone
from decimal import Decimal

from ownera.agent import MarketSnapshot
from ownera.domain import Decision
from ownera.external_provider import SubprocessStrategyProvider
from ownera.investment import InvestmentPolicy, PortfolioSnapshot
from ownera.investment_sandbox import InvestmentSandbox
from ownera.strategy_adapter import ValidatedStrategyAdapter
from ownera.treasury_cycle import AutonomousTreasuryCycle


def test_external_process_proposal_completes_sandbox_treasury_cycle():
    # The external process receives only a bounded market/portfolio snapshot
    # and emits a proposal. It has no execution or OWNERA authority interface.
    script = (
        "import json,sys; "
        "request=json.load(sys.stdin); "
        "price=request['market']['prices']['BTC']; "
        "print(json.dumps({'asset':'BTC','side':'BUY','quantity':'0.001',"
        "'price':price,'currency':'USD','rationale':'isolated provider test'}))"
    )
    provider = SubprocessStrategyProvider(
        [sys.executable, "-c", script],
        timeout_seconds=2,
        max_output_bytes=4096,
    )
    strategy = ValidatedStrategyAdapter(
        provider,
        allowed_assets={"BTC"},
        currency="USD",
        provider_id="external-process-test",
    )
    portfolio = PortfolioSnapshot("USD", Decimal("10000"))
    market = MarketSnapshot(
        {"BTC": Decimal("60000.00")},
        datetime(2026, 10, 27, 0, 0, tzinfo=timezone.utc),
    )
    sandbox = InvestmentSandbox(
        portfolio,
        InvestmentPolicy(
            max_single_trade=Decimal("500"),
            reserve_floor=Decimal("3000"),
            max_position_percent=Decimal("40"),
            max_daily_turnover=Decimal("1000"),
            currency="USD",
        ),
    )
    cycle = AutonomousTreasuryCycle(strategy, sandbox)

    result = cycle.run_once(
        market,
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
    assert result.outcome.integrity_verified is True
    assert sandbox.portfolio.cash == Decimal("9940.000")
