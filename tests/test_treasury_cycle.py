from datetime import datetime, timezone
from decimal import Decimal

from ownera.agent import AllocationTarget, AutonomousInvestmentAgent, MarketSnapshot
from ownera.domain import Decision
from ownera.investment import InvestmentPolicy, PortfolioSnapshot
from ownera.investment_sandbox import InvestmentSandbox
from ownera.treasury_cycle import AutonomousTreasuryCycle


def _cycle() -> AutonomousTreasuryCycle:
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
    agent = AutonomousInvestmentAgent(AllocationTarget("BTC", Decimal("5")), "USD")
    return AutonomousTreasuryCycle(agent, sandbox)


def test_autonomous_cycle_proposes_and_executes_under_authority() -> None:
    cycle = _cycle()
    result = cycle.run_once(
        MarketSnapshot(
            {"BTC": Decimal("60000")},
            datetime(2026, 10, 4, tzinfo=timezone.utc),
        )
    )

    assert result.proposal_created is True
    assert result.trade is not None
    assert result.trade.decision is Decision.ALLOW
    assert result.trade.committed is True
    assert result.trade.evidence is not None
    assert result.trade.evidence.verify_integrity()
    assert cycle.sandbox.portfolio.cash == Decimal("6650")


def test_autonomous_cycle_does_not_execute_when_policy_blocks_agent() -> None:
    cycle = _cycle()
    cycle.sandbox.policy = InvestmentPolicy(
        max_single_trade=Decimal("100"),
        reserve_floor=Decimal("3000"),
        max_position_percent=Decimal("40"),
        max_daily_turnover=Decimal("1000"),
        currency="USD",
    )

    result = cycle.run_once(
        MarketSnapshot(
            {"BTC": Decimal("60000")},
            datetime(2026, 10, 4, tzinfo=timezone.utc),
        )
    )

    assert result.proposal_created is True
    assert result.trade is not None
    assert result.trade.decision is Decision.DENY
    assert result.trade.committed is False
    assert cycle.sandbox.portfolio.cash == Decimal("7000")


def test_autonomous_cycle_second_observation_is_stable_at_target() -> None:
    sandbox = InvestmentSandbox(
        PortfolioSnapshot("USD", Decimal("6700"), ()),
        InvestmentPolicy(
            max_single_trade=Decimal("500"),
            reserve_floor=Decimal("3000"),
            max_position_percent=Decimal("40"),
            max_daily_turnover=Decimal("1000"),
            currency="USD",
        ),
    )
    agent = AutonomousInvestmentAgent(AllocationTarget("BTC", Decimal("5")), "USD")
    cycle = AutonomousTreasuryCycle(agent, sandbox)

    first = cycle.run_once(
        MarketSnapshot(
            {"BTC": Decimal("60000")},
            datetime(2026, 10, 4, tzinfo=timezone.utc),
        )
    )
    assert first.trade is not None
    assert first.trade.committed is True

    second = cycle.run_once(
        MarketSnapshot(
            {"BTC": Decimal("60000")},
            datetime(2026, 10, 4, 0, 1, tzinfo=timezone.utc),
        )
    )
    assert second.proposal_created is False
    assert second.trade is None


def test_cycle_rejects_stale_market_before_proposal() -> None:
    cycle = _cycle()
    result = cycle.run_once(
        MarketSnapshot(
            {"BTC": Decimal("60000")},
            datetime(2026, 10, 4, tzinfo=timezone.utc),
        ),
        now=datetime(2026, 10, 4, 0, 6, tzinfo=timezone.utc),
    )

    assert result.market_accepted is False
    assert result.rejection_reason == "market_data_stale"
    assert result.proposal_created is False
    assert result.trade is None
    assert cycle.sandbox.portfolio.cash == Decimal("7000")
    assert cycle.last_result is result


def test_cycle_remembers_verified_execution() -> None:
    cycle = _cycle()
    result = cycle.run_once(
        MarketSnapshot(
            {"BTC": Decimal("60000")},
            datetime(2026, 10, 4, tzinfo=timezone.utc),
        ),
        now=datetime(2026, 10, 4, 0, 1, tzinfo=timezone.utc),
    )

    assert result.verified is True
    assert cycle.history == (result,)
