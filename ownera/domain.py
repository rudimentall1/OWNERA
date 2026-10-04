"""Core domain types. Keep these provider-agnostic and deterministic."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from uuid import UUID, uuid4

from .financial_action import FinancialAction


class Decision(str, Enum):
    ALLOW = "ALLOW"
    DENY = "DENY"
    REVIEW = "REVIEW"


class RiskLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


@dataclass(frozen=True)
class Money:
    amount: Decimal
    currency: str


@dataclass(frozen=True)
class PaymentIntent:
    """A requested financial action before authorization or execution."""

    amount: Money
    destination: str
    purpose: str
    obligation_id: UUID | None = None
    id: UUID = field(default_factory=uuid4)
    idempotency_key: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_financial_action(self, agent_id: str) -> FinancialAction:
        if not agent_id.strip():
            raise ValueError("agent_id is required")
        if not self.idempotency_key:
            raise ValueError("idempotency key is required")
        return FinancialAction(
            intent_id=self.id,
            agent_id=agent_id,
            action_type="payment",
            destination=self.destination,
            amount=self.amount.amount,
            currency=self.amount.currency,
            purpose=self.purpose,
            idempotency_key=self.idempotency_key,
        )


@dataclass(frozen=True)
class InvestmentIntent:
    """An agent-proposed trade expressed as an authority-bound financial intent."""

    asset: str
    side: str
    quantity: Decimal
    price: Decimal
    currency: str
    rationale: str = ""
    id: UUID = field(default_factory=uuid4)
    idempotency_key: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def notional(self) -> Decimal:
        return self.quantity * self.price

    def to_financial_action(self, agent_id: str) -> FinancialAction:
        if not agent_id.strip():
            raise ValueError("agent_id is required")
        if not self.idempotency_key:
            raise ValueError("idempotency key is required")
        if self.quantity <= 0 or self.price <= 0:
            raise ValueError("quantity and price must be positive")
        if not self.asset.strip():
            raise ValueError("asset is required")
        return FinancialAction(
            intent_id=self.id,
            agent_id=agent_id,
            action_type=f"investment.{self.side.lower()}",
            destination=f"asset:{self.asset}",
            amount=self.notional,
            currency=self.currency,
            purpose=self.rationale,
            idempotency_key=self.idempotency_key,
            metadata={
                "asset": self.asset,
                "side": self.side.upper(),
                "quantity_exact": format(self.quantity, "f"),
                "price_exact": format(self.price, "f"),
            },
        )


@dataclass(frozen=True)
class PolicyResult:
    decision: Decision
    reasons: tuple[str, ...] = ()
    policy_version: str = "v0"


@dataclass(frozen=True)
class RiskResult:
    level: RiskLevel
    score: Decimal
    reasons: tuple[str, ...] = ()


@dataclass(frozen=True)
class AuthorizationResult:
    decision: Decision
    reasons: tuple[str, ...] = ()


@dataclass(frozen=True)
class ReserveInvariant:
    """Design invariant for the Sovereign Reserve."""

    agent_can_deposit: bool = True
    agent_can_withdraw: bool = False
    agent_can_transfer: bool = False
    agent_can_reconfigure: bool = False
