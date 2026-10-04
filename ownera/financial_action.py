"""Canonical financial action envelope for authority integrations."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
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
    metadata: dict[str, str] = field(default_factory=dict)

    def canonical_payload(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "intent_id": str(self.intent_id),
            "agent_id": self.agent_id,
            "action_type": self.action_type,
            "destination": self.destination,
            "amount": format(self.amount, "f"),
            "currency": self.currency,
            "purpose": self.purpose,
            "idempotency_key": self.idempotency_key,
        }
        if self.metadata:
            payload["metadata"] = dict(sorted(self.metadata.items()))
        return payload

    def digest(self) -> str:
        payload = json.dumps(
            self.canonical_payload(),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()
