"""Core domain types. Keep these provider-agnostic and deterministic."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from uuid import UUID, uuid4


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
    id: UUID = field(default_factory=uuid4)
    idempotency_key: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


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
