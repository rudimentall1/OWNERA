"""Automatic durable persistence facade for OWNERA commercial transitions."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from ownera.commercial import (
    CommercialAssessment,
    CommercialEngine,
    CommercialOpportunity,
    ProposalDraft,
    QualificationResult,
)
from ownera.commercial_repository import SQLiteCommercialRepository



class PersistentCommercialEngine:
    """Persists each successful commercial transition as a versioned snapshot."""

    def __init__(self, database_path: str) -> None:
        self.repository = SQLiteCommercialRepository(database_path)
        snapshot = self.repository.load()
        self._engine = snapshot.engine if snapshot else CommercialEngine()
        self._version = snapshot.version if snapshot else 0

    @property
    def version(self) -> int:
        return self._version

    @property
    def opportunities(self) -> tuple[CommercialOpportunity, ...]:
        return self._engine.opportunities

    @property
    def proposals(self) -> tuple[ProposalDraft, ...]:
        return self._engine.proposals

    def refresh(self) -> None:
        snapshot = self.repository.load()
        self._engine = snapshot.engine if snapshot else CommercialEngine()
        self._version = snapshot.version if snapshot else 0

    def _execute(self, operation):
        try:
            result = operation()
            self._version = self.repository.save(
                self._engine, expected_version=self._version
            )
            return result
        except Exception:
            self.refresh()
            raise

    def add_opportunity(self, opportunity: CommercialOpportunity) -> None:
        self._execute(lambda: self._engine.add_opportunity(opportunity))

    def assess(
        self, assessment: CommercialAssessment, *, now: datetime | None = None
    ) -> QualificationResult:
        return self._execute(lambda: self._engine.assess(assessment, now=now))

    def draft_proposal(self, proposal: ProposalDraft) -> ProposalDraft:
        return self._execute(lambda: self._engine.draft_proposal(proposal))

    def approve_proposal(
        self, proposal_id: UUID, owner_id: str, *, now: datetime | None = None
    ) -> ProposalDraft:
        return self._execute(
            lambda: self._engine.approve_proposal(proposal_id, owner_id, now=now)
        )
