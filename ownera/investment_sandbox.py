"""Autonomous investment simulation through the OWNERA authority boundary."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from uuid import uuid4

from .audit import AuditEvent, AuditLog
from .authority import AuthorityPort, LocalAuthorityAdapter
from .authorization import AuthorizationError, ExecutionAuthorization
from .domain import Decision
from .evidence import ExecutionEvidence
from .financial_action import FinancialAction
from .investment import (
    InvestmentDecision,
    InvestmentFirewall,
    InvestmentPolicy,
    PortfolioSnapshot,
    Position,
    TradeProposal,
)
from .receipt import ExecutionReceipt


@dataclass(frozen=True)
class SimulatedTrade:
    proposal: TradeProposal
    decision: Decision
    committed: bool
    portfolio_before: PortfolioSnapshot
    portfolio_after: PortfolioSnapshot
    authorization: ExecutionAuthorization | None = None
    financial_action: FinancialAction | None = None
    receipt: ExecutionReceipt | None = None
    evidence: ExecutionEvidence | None = None


class InvestmentSandbox:
    def __init__(
        self,
        portfolio: PortfolioSnapshot,
        policy: InvestmentPolicy,
        authority: AuthorityPort | None = None,
        audit: AuditLog | None = None,
    ) -> None:
        self.portfolio = portfolio
        self.policy = policy
        self._authority = authority or LocalAuthorityAdapter.create()
        self._audit = audit or AuditLog()
        self.daily_turnover = Decimal("0")

    @property
    def audit(self) -> AuditLog:
        return self._audit

    def propose_trade(self, proposal: TradeProposal) -> SimulatedTrade:
        before = self.portfolio
        result = InvestmentFirewall().evaluate(
            before, proposal, self.policy, daily_turnover=self.daily_turnover
        )
        verdict = InvestmentFirewall.authorization_decision(proposal, result)
        if result.decision is not InvestmentDecision.ALLOW:
            self._audit.append(
                AuditEvent(
                    event_type="investment.rejected",
                    actor="investment-firewall",
                    correlation_id=result.correlation_id,
                    payload_hash=f"proposal:{proposal.id}",
                    policy_version="investment-v1",
                )
            )
            return SimulatedTrade(proposal, verdict.decision, False, before, before)

        intent = proposal.to_intent()
        authorization = self._authority.issue(
            intent, verdict, policy_version="investment-v1"
        )
        try:
            self._authority.consume(authorization, intent)
        except AuthorizationError:
            self._audit.append(
                AuditEvent(
                    event_type="investment.rejected",
                    actor="authority",
                    correlation_id=authorization.correlation_id,
                    payload_hash=f"proposal:{proposal.id}",
                    policy_version="investment-v1",
                )
            )
            return SimulatedTrade(
                proposal, Decision.DENY, False, before, before, authorization=authorization
            )

        after = self._apply(proposal)
        self.portfolio = after
        self.daily_turnover += proposal.notional
        action = intent.to_financial_action(self._authority.agent_id)
        receipt = ExecutionReceipt.committed(
            authorization,
            amount=proposal.notional,
            currency=proposal.currency,
            destination=f"asset:{proposal.asset}",
        )
        evidence = ExecutionEvidence.from_execution(
            action, authorization, receipt, evidence_id=uuid4()
        )
        self._audit.append(
            AuditEvent(
                event_type="investment.committed",
                actor="investment-sandbox",
                correlation_id=authorization.correlation_id,
                payload_hash=evidence.evidence_sha256,
                policy_version=authorization.policy_version,
            )
        )
        return SimulatedTrade(
            proposal,
            Decision.ALLOW,
            True,
            before,
            after,
            authorization=authorization,
            financial_action=action,
            receipt=receipt,
            evidence=evidence,
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
                    position.asset,
                    position.quantity + proposal.quantity,
                    proposal.price,
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
