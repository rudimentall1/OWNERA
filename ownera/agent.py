"""Deterministic financial-agent proposal logic for the OWNERA sandbox.

The agent observes state and proposes an action. It never authorizes or executes.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from .investment import PortfolioSnapshot, TradeProposal, TradeSide


@dataclass(frozen=True)
class MarketSnapshot:
    prices: dict[str, Decimal]
    observed_at: datetime

    def __post_init__(self) -> None:
        if not self.prices:
            raise ValueError("at least one market price is required")
        for asset, price in self.prices.items():
            if not asset.strip():
                raise ValueError("market asset is required")
            if price <= 0:
                raise ValueError("market prices must be positive")

    def price(self, asset: str) -> Decimal:
        try:
            return self.prices[asset]
        except KeyError as exc:
            raise ValueError(f"market price unavailable for {asset}") from exc


@dataclass(frozen=True)
class AllocationTarget:
    asset: str
    target_percent: Decimal

    def __post_init__(self) -> None:
        if not self.asset.strip():
            raise ValueError("target asset is required")
        if not Decimal("0") <= self.target_percent <= Decimal("100"):
            raise ValueError("target_percent must be between 0 and 100")


class AutonomousInvestmentAgent:
    """Creates a bounded rebalance proposal from observed portfolio state."""

    def __init__(self, target: AllocationTarget, currency: str) -> None:
        if not currency.strip():
            raise ValueError("currency is required")
        self.target = target
        self.currency = currency

    def propose(
        self,
        portfolio: PortfolioSnapshot,
        market: MarketSnapshot,
    ) -> TradeProposal | None:
        if portfolio.currency != self.currency:
            raise ValueError("portfolio currency does not match agent currency")

        price = market.price(self.target.asset)
        total_value = portfolio.cash + sum(
            (
                position.quantity * price
                if position.asset == self.target.asset
                else position.value
                for position in portfolio.positions
            ),
            Decimal("0"),
        )
        if total_value <= 0:
            return None

        current_value = portfolio.position_value(self.target.asset)
        target_value = total_value * self.target.target_percent / Decimal("100")
        delta = target_value - current_value
        if delta == 0:
            return None

        side = TradeSide.BUY if delta > 0 else TradeSide.SELL
        notional = abs(delta)
        quantity = notional / price

        return TradeProposal(
            asset=self.target.asset,
            side=side,
            quantity=quantity,
            price=price,
            currency=self.currency,
            rationale=(
                f"rebalance {self.target.asset} toward "
                f"{self.target.target_percent}% target allocation"
            ),
        )
