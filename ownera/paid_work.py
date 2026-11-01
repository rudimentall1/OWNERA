"""Manual-first paid-work intake and qualification over the persistent commercial core.

This module deliberately does not scrape marketplaces, contact customers, submit
proposals, accept contracts, execute tasks, or record revenue.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid5

from ownera.commercial import (
    CommercialAssessment,
    CommercialOpportunity,
    ProposalDraft,
    QualificationResult,
)
from ownera.persistent_commercial import PersistentCommercialEngine


class PaidWorkError(RuntimeError):
    """A paid-work intake or transition is invalid."""


def _decimal(value: Any, field: str) -> Decimal:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise PaidWorkError(f"{field} must be a decimal number") from exc
    if not result.is_finite():
        raise PaidWorkError(f"{field} must be finite")
    return result


def _timestamp(value: Any, field: str, *, default_now: bool = False) -> datetime | None:
    if value is None:
        return datetime.now(timezone.utc) if default_now else None
    if not isinstance(value, str):
        raise PaidWorkError(f"{field} must be an ISO-8601 string")
    try:
        result = datetime.fromisoformat(value)
    except ValueError as exc:
        raise PaidWorkError(f"{field} must be an ISO-8601 timestamp") from exc
    if result.tzinfo is None:
        raise PaidWorkError(f"{field} must include a timezone")
    return result


class PaidWorkPipeline:
    """Thin application service over OWNERA's persistent commercial engine."""

    def __init__(self, database_path: str | Path) -> None:
        self.engine = PersistentCommercialEngine(str(database_path))

    @property
    def opportunities(self) -> tuple[CommercialOpportunity, ...]:
        return self.engine.opportunities

    @property
    def proposals(self) -> tuple[ProposalDraft, ...]:
        return self.engine.proposals

    def ingest(self, payload: dict[str, Any]) -> tuple[CommercialOpportunity, bool]:
        required = (
            "title", "description", "source_name", "source_url", "budget_min",
            "budget_max", "currency", "required_capabilities", "evidence_refs",
        )
        missing = [name for name in required if name not in payload]
        if missing:
            raise PaidWorkError(f"missing required fields: {', '.join(missing)}")
        source_url = str(payload["source_url"])
        try:
            opportunity_id = UUID(str(payload["opportunity_id"])) if payload.get(
                "opportunity_id"
            ) else uuid5(NAMESPACE_URL, f"ownera-paid-work:{source_url}")
        except ValueError as exc:
            raise PaidWorkError("opportunity_id must be a UUID") from exc
        capabilities = payload["required_capabilities"]
        evidence_refs = payload["evidence_refs"]
        if not isinstance(capabilities, list) or not all(
            isinstance(item, str) and item.strip() for item in capabilities
        ):
            raise PaidWorkError("required_capabilities must be a list of non-empty strings")
        if not isinstance(evidence_refs, list) or not all(
            isinstance(item, str) and item.strip() for item in evidence_refs
        ):
            raise PaidWorkError("evidence_refs must be a list of non-empty strings")
        opportunity = CommercialOpportunity(
            opportunity_id=opportunity_id,
            title=str(payload["title"]),
            description=str(payload["description"]),
            source_name=str(payload["source_name"]),
            source_url=source_url,
            budget_min=_decimal(payload["budget_min"], "budget_min"),
            budget_max=_decimal(payload["budget_max"], "budget_max"),
            currency=str(payload["currency"]).upper(),
            required_capabilities=frozenset(capabilities),
            evidence_refs=tuple(evidence_refs),
            discovered_at=_timestamp(payload.get("discovered_at"), "discovered_at", default_now=True),
            deadline=_timestamp(payload.get("deadline"), "deadline"),
        )
        existing = next(
            (item for item in self.engine.opportunities if item.opportunity_id == opportunity_id),
            None,
        )
        if existing is not None:
            comparable_existing = (
                existing.title, existing.description, existing.source_name,
                existing.source_url, existing.budget_min, existing.budget_max,
                existing.currency, existing.required_capabilities, existing.evidence_refs,
                existing.deadline,
            )
            comparable_new = (
                opportunity.title, opportunity.description, opportunity.source_name,
                opportunity.source_url, opportunity.budget_min, opportunity.budget_max,
                opportunity.currency, opportunity.required_capabilities,
                opportunity.evidence_refs, opportunity.deadline,
            )
            if comparable_existing != comparable_new:
                raise PaidWorkError(
                    "source URL already exists with different terms; review it manually "
                    "instead of silently overwriting the record"
                )
            return existing, False
        self.engine.add_opportunity(opportunity)
        return opportunity, True

    def assess(
        self,
        opportunity_id: UUID,
        *,
        delivery_cost: Decimal,
        platform_fee_rate: Decimal,
        contingency_rate: Decimal,
        win_probability: Decimal,
        minimum_net_margin: Decimal,
        terms_reviewed: bool,
        eligibility_confirmed: bool,
    ) -> QualificationResult:
        assessment = CommercialAssessment(
            opportunity_id=opportunity_id,
            estimated_delivery_cost=delivery_cost,
            platform_fee_rate=platform_fee_rate,
            contingency_rate=contingency_rate,
            win_probability=win_probability,
            minimum_net_margin=minimum_net_margin,
            terms_reviewed=terms_reviewed,
            eligibility_confirmed=eligibility_confirmed,
        )
        return self.engine.assess(assessment)

    def draft_proposal(self, payload: dict[str, Any]) -> ProposalDraft:
        required = ("opportunity_id", "scope", "acceptance_criteria", "delivery_plan", "quote_amount", "currency")
        missing = [name for name in required if name not in payload]
        if missing:
            raise PaidWorkError(f"proposal is missing fields: {', '.join(missing)}")
        try:
            opportunity_id = UUID(str(payload["opportunity_id"]))
        except ValueError as exc:
            raise PaidWorkError("proposal requires a valid opportunity_id") from exc
        criteria = payload["acceptance_criteria"]
        plan = payload["delivery_plan"]
        if not isinstance(criteria, list) or not all(isinstance(item, str) and item.strip() for item in criteria):
            raise PaidWorkError("acceptance_criteria must be a list of non-empty strings")
        if not isinstance(plan, list) or not all(isinstance(item, str) and item.strip() for item in plan):
            raise PaidWorkError("delivery_plan must be a list of non-empty strings")
        proposal = ProposalDraft(
            opportunity_id=opportunity_id,
            scope=str(payload["scope"]),
            acceptance_criteria=tuple(criteria),
            delivery_plan=tuple(plan),
            quote_amount=_decimal(payload["quote_amount"], "quote_amount"),
            currency=str(payload["currency"]).upper(),
        )
        return self.engine.draft_proposal(proposal)

    def get_opportunity(self, opportunity_id: UUID) -> CommercialOpportunity:
        for item in self.engine.opportunities:
            if item.opportunity_id == opportunity_id:
                return item
        raise PaidWorkError(f"unknown opportunity: {opportunity_id}")

    def get_proposal(self, proposal_id: UUID) -> ProposalDraft:
        for item in self.engine.proposals:
            if item.proposal_id == proposal_id:
                return item
        raise PaidWorkError(f"unknown proposal: {proposal_id}")
