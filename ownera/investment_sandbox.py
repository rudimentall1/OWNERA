"""Autonomous investment simulation through the OWNERA authority boundary."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from .authority import AuthorityPort, LocalAuthorityAdapter
from .authorization import AuthorizationError, ExecutionAuthorization
from .domain import Decision
from .investment import (
    InvestmentDecision,
    InvestmentFirewall,
    InvestmentPolicy,
    PortfolioSnapshot,
    Position,
    TradeProposal,
)
from .financial_action import FinancialAction


@dataclass(frozen=True)
class SimulatedTrade:
    proposal: TradeProposal
    decision: Decision
    committed: bool
    portfolio_before: PortfolioSnapshot
    portfolio_after: PortfolioSnapshot
    authorization: ExecutionAuthorization | None = None
    financial_action: FinancialAction | None = None


class InvestmentSandbox:
    def __init__(
        self,
        portfolio: PortfolioSnapshot,
        policy: InvestmentPolicy,
        authority: AuthorityPort | None = None,
    ) -> None:
        self.portfolio = portfolio
        self.policy = policy
        self._authority = authority or LocalAuthorityAdapter.create()
        self.daily_turnover = Decimal("0")

    def propose_trade(self, proposal: TradeProposal) -> SimulatedTrade:
        before = self.portfolio
        result = InvestmentFirewall().evaluate(
            before,
            proposal,
            self.policy,
            daily_turnover=self.daily_turnover,
        )
        verdict = InvestmentFirewall.authorization_decision(proposal, result)
        if result.decision is not InvestmentDecision.ALLOW:
            return SimulatedTrade(proposal, verdict.decision, False, before, before)

        intent = proposal.to_intent()
        authorization = self._authority.issue(
            intent,
            verdict,
            policy_version="investment-v1",
        )
        try:
            self._authority.consume(authorization, intent)
        except AuthorizationError:
            return SimulatedTrade(
                proposal,
                Decision.DENY,
                False,
                before,
                before,
                authorization=authorization,
            )

        self.portfolio = self._apply(proposal)
        self.daily_turnover += proposal.notional
        action = intent.to_financial_action(self._authority.agent_id)
        return SimulatedTrade(
            proposal,
            Decision.ALLOW,
            True,
            before,
            self.portfolio,
            authorization=authorization,
            financial_action=action,
        )

    def _apply(self, proposal: TradeProposal) -> PortfolioSnapshot:
        cash = self.portfolio.cash
        positions = list(self.portfolio.positions)
        existing = next(
            (index for index, position in enumerate(positions) if position.asset == proposal.asset),
            None,
        )

        if proposal.side.value == "BUY":
            cash -= proposal.notional
            if existing is None:
                positions.append(Position(proposal.asset, proposal.quantity, proposal.price))
            else:
                position = positions[existing]
                positions[existing] = Position(
                    asset=position.asset,
                    quantity=position.quantity + proposal.quantity,
                    price=proposal.price,
                )
        else:
            cash += proposal.notional
            if existing is None:
                raise ValueError("position disappeared during execution")
            position = positions[existing]
            remaining = position.quantity - proposal.quantity
            positions[existing] = Position(position.asset, remaining, proposal.price)

        return PortfolioSnapshot(
            currency=self.portfolio.currency,
            cash=cash,
            positions=tuple(position for position in positions if position.quantity > 0),
        )
