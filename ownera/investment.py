"""Deterministic investment decision primitives for the OWNERA sandbox.

This module deliberately contains no market-data client and no model integration.
An agent may propose a trade, but OWNERA evaluates the proposal against explicit
portfolio constraints before it can reach execution.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum


class TradeSide(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class InvestmentDecision(str, Enum):
    ALLOW = "ALLOW"
    REVIEW = "REVIEW"
    DENY = "DENY"


@dataclass(frozen=True)
class Position:
    asset: str
    quantity: Decimal
    price: Decimal

    def __post_init__(self) -> None:
        if not self.asset:
            raise ValueError("asset is required")
        if self.quantity < 0:
            raise ValueError("quantity cannot be negative")
        if self.price < 0:
            raise ValueError("price cannot be negative")

    @property
    def value(self) -> Decimal:
        return self.quantity * self.price


@dataclass(frozen=True)
class PortfolioSnapshot:
    currency: str
    cash: Decimal
    positions: tuple[Position, ...] = ()

    def __post_init__(self) -> None:
        if not self.currency:
            raise ValueError("currency is required")
        if self.cash < 0:
            raise ValueError("cash cannot be negative")

    @property
    def invested_value(self) -> Decimal:
        return sum((position.value for position in self.positions), Decimal("0"))

    @property
    def total_value(self) -> Decimal:
        return self.cash + self.invested_value

    def position_value(self, asset: str) -> Decimal:
        return sum(
            (position.value for position in self.positions if position.asset == asset),
            Decimal("0"),
        )


@dataclass(frozen=True)
class TradeProposal:
    asset: str
    side: TradeSide
    quantity: Decimal
    price: Decimal
    currency: str
    rationale: str = ""

    def __post_init__(self) -> None:
        if not self.asset:
            raise ValueError("asset is required")
        if self.quantity <= 0:
            raise ValueError("quantity must be positive")
        if self.price <= 0:
            raise ValueError("price must be positive")
        if not self.currency:
            raise ValueError("currency is required")

    @property
    def notional(self) -> Decimal:
        return self.quantity * self.price


@dataclass(frozen=True)
class InvestmentPolicy:
    max_single_trade: Decimal
    reserve_floor: Decimal
    max_position_percent: Decimal
    max_daily_turnover: Decimal
    currency: str

    def __post_init__(self) -> None:
        if self.max_single_trade <= 0:
            raise ValueError("max_single_trade must be positive")
        if self.reserve_floor < 0:
            raise ValueError("reserve_floor cannot be negative")
        if not Decimal("0") < self.max_position_percent <= Decimal("100"):
            raise ValueError("max_position_percent must be between 0 and 100")
        if self.max_daily_turnover <= 0:
            raise ValueError("max_daily_turnover must be positive")
        if not self.currency:
            raise ValueError("currency is required")


@dataclass(frozen=True)
class InvestmentDecisionResult:
    decision: InvestmentDecision
    reason: str


class InvestmentFirewall:
    """Fail-closed evaluation of an agent-proposed portfolio trade."""

    def evaluate(
        self,
        portfolio: PortfolioSnapshot,
        proposal: TradeProposal,
        policy: InvestmentPolicy,
        daily_turnover: Decimal = Decimal("0"),
    ) -> InvestmentDecisionResult:
        if proposal.currency != policy.currency or portfolio.currency != policy.currency:
            return InvestmentDecisionResult(
                InvestmentDecision.DENY, "currency_mismatch"
            )
        if daily_turnover < 0:
            return InvestmentDecisionResult(
                InvestmentDecision.DENY, "invalid_daily_turnover"
            )
        if proposal.notional > policy.max_single_trade:
            return InvestmentDecisionResult(
                InvestmentDecision.DENY, "single_trade_limit"
            )
        if daily_turnover + proposal.notional > policy.max_daily_turnover:
            return InvestmentDecisionResult(
                InvestmentDecision.DENY, "daily_turnover_limit"
            )

        if proposal.side is TradeSide.BUY:
            if portfolio.cash - proposal.notional < policy.reserve_floor:
                return InvestmentDecisionResult(
                    InvestmentDecision.DENY, "reserve_floor"
                )
            projected_value = portfolio.position_value(proposal.asset) + proposal.notional
        else:
            held_value = portfolio.position_value(proposal.asset)
            if proposal.notional > held_value:
                return InvestmentDecisionResult(
                    InvestmentDecision.DENY, "insufficient_position"
                )
            projected_value = held_value - proposal.notional

        total_value = portfolio.total_value
        if total_value <= 0:
            return InvestmentDecisionResult(
                InvestmentDecision.DENY, "empty_portfolio"
            )

        projected_percent = (projected_value / total_value) * Decimal("100")
        if projected_percent > policy.max_position_percent:
            return InvestmentDecisionResult(
                InvestmentDecision.DENY, "position_concentration"
            )

        return InvestmentDecisionResult(InvestmentDecision.ALLOW, "policy_satisfied")
