"""Immutable treasury outcomes linking a decision to what execution produced.

An outcome records what OWNERA observed. It does not by itself prove that an
external broker, bank, or chain produced the claimed real-world effect.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from .domain import Decision
from .investment_sandbox import SimulatedTrade


@dataclass(frozen=True)
class TreasuryOutcome:
    cycle_id: UUID
    status: str
    decision: Decision | None
    intent_id: UUID | None
    authorization_id: UUID | None
    evidence_sha256: str | None
    observed_at: datetime
    source: str
    integrity_verified: bool = False

    @classmethod
    def from_trade(
        cls,
        cycle_id: UUID,
        trade: SimulatedTrade,
        *,
        observed_at: datetime,
    ) -> TreasuryOutcome:
        authorization_id = (
            trade.authorization.id if trade.authorization is not None else None
        )
        intent_id = trade.proposal.id if trade.committed else None
        evidence = trade.evidence
        return cls(
            cycle_id=cycle_id,
            status="EXECUTED" if trade.committed else "REJECTED",
            decision=trade.decision,
            intent_id=intent_id,
            authorization_id=authorization_id,
            evidence_sha256=evidence.evidence_sha256 if evidence else None,
            observed_at=observed_at,
            source="sandbox-execution" if trade.committed else "authority-or-policy",
            integrity_verified=(
                evidence is not None and evidence.verify_integrity()
            ),
        )

    @classmethod
    def no_action(
        cls,
        cycle_id: UUID,
        *,
        decision: Decision,
        observed_at: datetime,
        source: str,
    ) -> TreasuryOutcome:
        return cls(
            cycle_id=cycle_id,
            status="NO_ACTION",
            decision=decision,
            intent_id=None,
            authorization_id=None,
            evidence_sha256=None,
            observed_at=observed_at,
            source=source,
        )
