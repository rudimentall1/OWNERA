"""Automatic durable persistence facade for OWNERA commercial transitions."""

from __future__ import annotations

import hashlib
import json
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
        self._event_version = len(
            self.repository.event_store.load("commercial_pipeline", "primary")
        )

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
        self._event_version = len(
            self.repository.event_store.load("commercial_pipeline", "primary")
        )

    def _execute(self, operation, *, event_type: str, aggregate_id: str, payload: dict):
        try:
            result = operation()
            canonical = json.dumps(
                payload, sort_keys=True, separators=(",", ":"),
                ensure_ascii=False, allow_nan=False,
            )
            key_digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
            self._version, event = self.repository.save_with_event(
                self._engine,
                expected_version=self._version,
                expected_event_version=self._event_version,
                event_type=event_type,
                aggregate_id=aggregate_id,
                payload=payload,
                idempotency_key=f"{event_type}:{aggregate_id}:{key_digest}",
            )
            self._event_version = event.version
            return result
        except Exception:
            self.refresh()
            raise

    def add_opportunity(self, opportunity: CommercialOpportunity) -> None:
        self._execute(
            lambda: self._engine.add_opportunity(opportunity),
            event_type="OpportunityDiscovered",
            aggregate_id="primary",
            payload={
                "opportunity_id": str(opportunity.opportunity_id),
                "title": opportunity.title,
                "source_name": opportunity.source_name,
                "source_url": opportunity.source_url,
                "budget_min": str(opportunity.budget_min),
                "budget_max": str(opportunity.budget_max),
                "currency": opportunity.currency,
                "evidence_refs": list(opportunity.evidence_refs),
            },
        )

    def assess(
        self, assessment: CommercialAssessment, *, now: datetime | None = None
    ) -> QualificationResult:
        return self._execute(
            lambda: self._engine.assess(assessment, now=now),
            event_type="OpportunityAssessed",
            aggregate_id="primary",
            payload={
                "opportunity_id": str(assessment.opportunity_id),
                "estimated_delivery_cost": str(assessment.estimated_delivery_cost),
                "platform_fee_rate": str(assessment.platform_fee_rate),
                "contingency_rate": str(assessment.contingency_rate),
                "win_probability": str(assessment.win_probability),
                "minimum_net_margin": str(assessment.minimum_net_margin),
                "terms_reviewed": assessment.terms_reviewed,
                "eligibility_confirmed": assessment.eligibility_confirmed,
            },
        )

    def draft_proposal(self, proposal: ProposalDraft) -> ProposalDraft:
        return self._execute(
            lambda: self._engine.draft_proposal(proposal),
            event_type="ProposalDrafted",
            aggregate_id="primary",
            payload={
                "proposal_id": str(proposal.proposal_id),
                "opportunity_id": str(proposal.opportunity_id),
                "quote_amount": str(proposal.quote_amount),
                "currency": proposal.currency,
                "scope": proposal.scope,
                "acceptance_criteria": list(proposal.acceptance_criteria),
            },
        )

    def approve_proposal(
        self, proposal_id: UUID, owner_id: str, *, now: datetime | None = None
    ) -> ProposalDraft:
        return self._execute(
            lambda: self._engine.approve_proposal(proposal_id, owner_id, now=now),
            event_type="ProposalOwnerApproved",
            aggregate_id="primary",
            payload={"proposal_id": str(proposal_id), "owner_id": owner_id},
        )
