"""Canonical financial action envelope for authority integrations.

The treasury keeps monetary values as exact decimal strings at the authority
boundary. External authority providers must bind the exact amount, currency,
destination, and intent identity; binary floating-point conversion is never
performed here.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID


@dataclass(frozen=True)
class FinancialAction:
    intent_id: UUID
    agent_id: str
    action_type: str
    destination: str
    amount: Decimal
    currency: str
    purpose: str
    idempotency_key: str

    def canonical_payload(self) -> dict[str, str]:
        return {
            "intent_id": str(self.intent_id),
            "agent_id": self.agent_id,
            "action_type": self.action_type,
            "destination": self.destination,
            "amount": format(self.amount, "f"),
            "currency": self.currency,
            "purpose": self.purpose,
            "idempotency_key": self.idempotency_key,
        }

    def digest(self) -> str:
        payload = json.dumps(
            self.canonical_payload(),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()
