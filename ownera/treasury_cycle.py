"""Stateful autonomous OWNERA treasury decision/execution cycle."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from .agent import AutonomousInvestmentAgent, MarketSnapshot
from .investment_sandbox import InvestmentSandbox, SimulatedTrade


@dataclass(frozen=True)
class TreasuryCycleResult:
    proposal_created: bool
    trade: SimulatedTrade | None
    observed_at: datetime
    market_accepted: bool = True
    rejection_reason: str | None = None

    @property
    def verified(self) -> bool:
        return self.trade is not None and self.trade.committed and self.trade.evidence is not None and self.trade.evidence.verify_integrity()


class AutonomousTreasuryCycle:
    """Observe, decide, authorize, execute, verify, and remember each cycle."""

    def __init__(
        self,
        agent: AutonomousInvestmentAgent,
        sandbox: InvestmentSandbox,
        *,
        max_market_age: timedelta = timedelta(minutes=5),
    ) -> None:
        if max_market_age <= timedelta(0):
            raise ValueError("max_market_age must be positive")
        self._agent = agent
        self._sandbox = sandbox
        self._max_market_age = max_market_age
        self._history: list[TreasuryCycleResult] = []

    @property
    def sandbox(self) -> InvestmentSandbox:
        return self._sandbox

    @property
    def history(self) -> tuple[TreasuryCycleResult, ...]:
        return tuple(self._history)

    @property
    def last_result(self) -> TreasuryCycleResult | None:
        return self._history[-1] if self._history else None

    def run_once(
        self,
        market: MarketSnapshot,
        *,
        now: datetime | None = None,
    ) -> TreasuryCycleResult:
        current_time = now or datetime.now(timezone.utc)
        if current_time.tzinfo is None:
            raise ValueError("now must be timezone-aware")
        if market.observed_at.tzinfo is None:
            raise ValueError("market.observed_at must be timezone-aware")
        if market.observed_at > current_time:
            result = TreasuryCycleResult(
                False,
                None,
                market.observed_at,
                market_accepted=False,
                rejection_reason="market_timestamp_in_future",
            )
            self._remember(result)
            return result
        if current_time - market.observed_at > self._max_market_age:
            result = TreasuryCycleResult(
                False,
                None,
                market.observed_at,
                market_accepted=False,
                rejection_reason="market_data_stale",
            )
            self._remember(result)
            return result

        proposal = self._agent.propose(self._sandbox.portfolio, market)
        if proposal is None:
            result = TreasuryCycleResult(False, None, market.observed_at)
            self._remember(result)
            return result

        trade = self._sandbox.propose_trade(proposal)
        result = TreasuryCycleResult(True, trade, market.observed_at)
        self._remember(result)
        return result

    def _remember(self, result: TreasuryCycleResult) -> None:
        self._history.append(result)
