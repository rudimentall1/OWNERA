"""One autonomous OWNERA treasury decision/execution cycle."""

from __future__ import annotations

from dataclasses import dataclass

from .agent import AutonomousInvestmentAgent, MarketSnapshot
from .investment_sandbox import InvestmentSandbox, SimulatedTrade


@dataclass(frozen=True)
class TreasuryCycleResult:
    proposal_created: bool
    trade: SimulatedTrade | None


class AutonomousTreasuryCycle:
    """Separates observation/proposal from deterministic authority and execution."""

    def __init__(
        self,
        agent: AutonomousInvestmentAgent,
        sandbox: InvestmentSandbox,
    ) -> None:
        self._agent = agent
        self._sandbox = sandbox

    @property
    def sandbox(self) -> InvestmentSandbox:
        return self._sandbox

    def run_once(self, market: MarketSnapshot) -> TreasuryCycleResult:
        proposal = self._agent.propose(self._sandbox.portfolio, market)
        if proposal is None:
            return TreasuryCycleResult(False, None)

        trade = self._sandbox.propose_trade(proposal)
        return TreasuryCycleResult(True, trade)
