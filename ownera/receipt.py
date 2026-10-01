"""Execution receipts for the OWNERA financial sandbox.

A receipt records the authorization and observed sandbox outcome so an action
can be reconstructed without treating the AI as the source of truth.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

from .authorization import ExecutionAuthorization


@dataclass(frozen=True)
class ExecutionReceipt:
    authorization_id: UUID
    intent_id: UUID
    correlation_id: UUID
    status: str
    amount: Decimal
    currency: str
    destination: str
    policy_version: str
    executed_at: datetime

    @classmethod
    def committed(
        cls,
        authorization: ExecutionAuthorization,
        *,
        amount: Decimal,
        currency: str,
        destination: str,
        executed_at: datetime | None = None,
    ) -> ExecutionReceipt:
        return cls(
            authorization_id=authorization.id,
            intent_id=authorization.intent_id,
            correlation_id=authorization.correlation_id,
            status="COMMITTED",
            amount=amount,
            currency=currency,
            destination=destination,
            policy_version=authorization.policy_version,
            executed_at=executed_at or datetime.now(timezone.utc),
        )
