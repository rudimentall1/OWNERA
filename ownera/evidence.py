"""Tamper-evident execution evidence for OWNERA financial actions.

Evidence is a portable, deterministic manifest linking the exact financial
action, authorization artifact, and observed execution receipt. It is not a
claim that an external provider is honest; it is a cryptographic commitment
to what OWNERA observed.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from .authorization import ExecutionAuthorization
from .financial_action import FinancialAction
from .receipt import ExecutionReceipt


def _canonical(payload: dict[str, object]) -> bytes:
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def _sha256(payload: dict[str, object]) -> str:
    return hashlib.sha256(_canonical(payload)).hexdigest()


def _authorization_payload(authorization: ExecutionAuthorization) -> dict[str, object]:
    provider_authorization = authorization.provider_authorization
    return {
        "id": str(authorization.id),
        "intent_id": str(authorization.intent_id),
        "correlation_id": str(authorization.correlation_id),
        "policy_version": authorization.policy_version,
        "issued_at": authorization.issued_at.isoformat(),
        "expires_at": authorization.expires_at.isoformat(),
        "nonce": authorization.nonce,
        "provider": authorization.provider,
        "provider_authorization": provider_authorization,
    }


@dataclass(frozen=True)
class ExecutionEvidence:
    version: int
    evidence_id: UUID
    intent_id: UUID
    correlation_id: UUID
    financial_action_sha256: str
    authorization_sha256: str
    authorization_id: UUID
    provider: str
    status: str
    amount: Decimal
    currency: str
    destination: str
    policy_version: str
    executed_at: datetime
    evidence_sha256: str

    @classmethod
    def from_execution(
        cls,
        action: FinancialAction,
        authorization: ExecutionAuthorization,
        receipt: ExecutionReceipt,
        *,
        evidence_id: UUID,
    ) -> ExecutionEvidence:
        if action.intent_id != receipt.intent_id:
            raise ValueError("financial action and receipt intent mismatch")
        if authorization.intent_id != receipt.intent_id:
            raise ValueError("authorization and receipt intent mismatch")
        if authorization.id != receipt.authorization_id:
            raise ValueError("authorization and receipt mismatch")
        if receipt.amount != action.amount:
            raise ValueError("receipt amount does not match financial action")
        if receipt.currency != action.currency:
            raise ValueError("receipt currency does not match financial action")
        if receipt.destination != action.destination:
            raise ValueError("receipt destination does not match financial action")

        action_hash = action.digest()
        authorization_hash = _sha256(_authorization_payload(authorization))
        unsigned = {
            "version": 1,
            "evidence_id": str(evidence_id),
            "intent_id": str(receipt.intent_id),
            "correlation_id": str(receipt.correlation_id),
            "financial_action_sha256": action_hash,
            "authorization_sha256": authorization_hash,
            "authorization_id": str(receipt.authorization_id),
            "provider": authorization.provider,
            "status": receipt.status,
            "amount": format(receipt.amount, "f"),
            "currency": receipt.currency,
            "destination": receipt.destination,
            "policy_version": receipt.policy_version,
            "executed_at": receipt.executed_at.isoformat(),
        }
        return cls(
            version=1,
            evidence_id=evidence_id,
            intent_id=receipt.intent_id,
            correlation_id=receipt.correlation_id,
            financial_action_sha256=action_hash,
            authorization_sha256=authorization_hash,
            authorization_id=receipt.authorization_id,
            provider=authorization.provider,
            status=receipt.status,
            amount=receipt.amount,
            currency=receipt.currency,
            destination=receipt.destination,
            policy_version=receipt.policy_version,
            executed_at=receipt.executed_at,
            evidence_sha256=_sha256(unsigned),
        )

    def manifest(self) -> dict[str, object]:
        return {
            "version": self.version,
            "evidence_id": str(self.evidence_id),
            "intent_id": str(self.intent_id),
            "correlation_id": str(self.correlation_id),
            "financial_action_sha256": self.financial_action_sha256,
            "authorization_sha256": self.authorization_sha256,
            "authorization_id": str(self.authorization_id),
            "provider": self.provider,
            "status": self.status,
            "amount": format(self.amount, "f"),
            "currency": self.currency,
            "destination": self.destination,
            "policy_version": self.policy_version,
            "executed_at": self.executed_at.isoformat(),
            "evidence_sha256": self.evidence_sha256,
        }

    def verify_integrity(self) -> bool:
        manifest = self.manifest()
        claimed = manifest.pop("evidence_sha256")
        return claimed == _sha256(manifest)
