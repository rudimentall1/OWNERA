"""Provider-neutral financial domain model for OWNERA.

These types describe what the treasury owns, owes, must pay, and holds.
They contain no bank, broker, blockchain, model, or provider assumptions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from enum import Enum
from uuid import UUID, uuid4


class AssetKind(str, Enum):
    CASH = "CASH"
    STABLECOIN = "STABLECOIN"
    CRYPTO = "CRYPTO"
    SECURITY = "SECURITY"
    RWA = "RWA"


class AccountKind(str, Enum):
    CASH = "CASH"
    INVESTMENT = "INVESTMENT"
    CRYPTO = "CRYPTO"
    RESERVE = "RESERVE"


class LiabilityKind(str, Enum):
    DEBT = "DEBT"
    CREDIT = "CREDIT"
    OTHER = "OTHER"


class ObligationStatus(str, Enum):
    SCHEDULED = "SCHEDULED"
    DUE = "DUE"
    PAID = "PAID"
    CANCELLED = "CANCELLED"


@dataclass(frozen=True)
class Asset:
    symbol: str
    kind: AssetKind
    decimals: int = 2
    id: UUID = field(default_factory=uuid4)

    def __post_init__(self) -> None:
        if not self.symbol.strip():
            raise ValueError("asset symbol is required")
        if self.decimals < 0:
            raise ValueError("asset decimals cannot be negative")


@dataclass(frozen=True)
class Account:
    name: str
    kind: AccountKind
    currency: str
    id: UUID = field(default_factory=uuid4)

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("account name is required")
        if not self.currency.strip():
            raise ValueError("account currency is required")


@dataclass(frozen=True)
class Balance:
    account_id: UUID
    asset_id: UUID
    quantity: Decimal

    def __post_init__(self) -> None:
        if self.quantity < 0:
            raise ValueError("balance quantity cannot be negative")


@dataclass(frozen=True)
class Liability:
    name: str
    kind: LiabilityKind
    amount: Decimal
    currency: str
    due_date: date | None = None
    id: UUID = field(default_factory=uuid4)

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("liability name is required")
        if self.amount < 0:
            raise ValueError("liability amount cannot be negative")
        if not self.currency.strip():
            raise ValueError("liability currency is required")


@dataclass(frozen=True)
class Obligation:
    name: str
    amount: Decimal
    currency: str
    due_date: date
    destination: str
    status: ObligationStatus = ObligationStatus.SCHEDULED
    id: UUID = field(default_factory=uuid4)

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("obligation name is required")
        if self.amount <= 0:
            raise ValueError("obligation amount must be positive")
        if not self.currency.strip():
            raise ValueError("obligation currency is required")
        if not self.destination.strip():
            raise ValueError("obligation destination is required")


@dataclass(frozen=True)
class Position:
    account_id: UUID
    asset_id: UUID
    quantity: Decimal
    average_cost: Decimal | None = None
    id: UUID = field(default_factory=uuid4)

    def __post_init__(self) -> None:
        if self.quantity < 0:
            raise ValueError("position quantity cannot be negative")
        if self.average_cost is not None and self.average_cost < 0:
            raise ValueError("average cost cannot be negative")
