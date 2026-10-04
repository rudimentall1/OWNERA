"""Stateful autonomous OWNERA treasury decision/execution cycle."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from .agent import AutonomousInvestmentAgent, MarketSnapshot
from .domain import Decision
from .investment_sandbox import InvestmentSandbox, SimulatedTrade
from .outcome import TreasuryOutcome


@dataclass(frozen=True)
class TreasuryCycleResult:
    cycle_id: UUID
    proposal_created: bool
    trade: SimulatedTrade | None
    observed_at: datetime
    market_sha256: str
    decision: Decision | None = None
    rationale: str | None = None
    evidence_sha256: str | None = None
    market_accepted: bool = True
    rejection_reason: str | None = None
    outcome: TreasuryOutcome | None = None

    @property
    def verified(self) -> bool:
        return (
            self.trade is not None
            and self.trade.committed
            and self.trade.evidence is not None
            and self.trade.evidence.verify_integrity()
        )


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

        cycle_id = uuid4()
        market_sha256 = self._market_digest(market)

        if market.observed_at > current_time:
            result = TreasuryCycleResult(
                cycle_id,
                False,
                None,
                market.observed_at,
                market_sha256,
                market_accepted=False,
                rejection_reason="market_timestamp_in_future",
                outcome=TreasuryOutcome.no_action(
                    cycle_id,
                    decision=Decision.DENY,
                    observed_at=current_time,
                    source="market-validation",
                ),
            )
            self._remember(result)
            return result

        if current_time - market.observed_at > self._max_market_age:
            result = TreasuryCycleResult(
                cycle_id,
                False,
                None,
                market.observed_at,
                market_sha256,
                market_accepted=False,
                rejection_reason="market_data_stale",
                outcome=TreasuryOutcome.no_action(
                    cycle_id,
                    decision=Decision.DENY,
                    observed_at=current_time,
                    source="market-validation",
                ),
            )
            self._remember(result)
            return result

        proposal = self._agent.propose(self._sandbox.portfolio, market)
        if proposal is None:
            result = TreasuryCycleResult(
                cycle_id,
                False,
                None,
                market.observed_at,
                market_sha256,
                decision=Decision.ALLOW,
                rationale="portfolio already satisfies the configured allocation target",
                outcome=TreasuryOutcome.no_action(
                    cycle_id,
                    decision=Decision.ALLOW,
                    observed_at=current_time,
                    source="decision-engine",
                ),
            )
            self._remember(result)
            return result

        trade = self._sandbox.propose_trade(proposal)
        result = TreasuryCycleResult(
            cycle_id,
            True,
            trade,
            market.observed_at,
            market_sha256,
            decision=trade.decision,
            rationale=proposal.rationale,
            evidence_sha256=trade.evidence.evidence_sha256 if trade.evidence else None,
            outcome=TreasuryOutcome.from_trade(
                cycle_id,
                trade,
                observed_at=current_time,
            ),
        )
        self._remember(result)
        return result

    @staticmethod
    def _market_digest(market: MarketSnapshot) -> str:
        payload = {
            "observed_at": market.observed_at.isoformat(),
            "prices": {
                asset: format(price, "f")
                for asset, price in sorted(market.prices.items())
            },
        }
        encoded = json.dumps(
            payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def _remember(self, result: TreasuryCycleResult) -> None:
        self._history.append(result)
