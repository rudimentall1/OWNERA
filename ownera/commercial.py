"""Deterministic commercial opportunity qualification for OWNERA.

This module evaluates sourced opportunities and prepares proposal drafts. It does
not scrape marketplaces, contact customers, submit offers, sign contracts, or
move money. External commitments require a separate owner-approved adapter.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from urllib.parse import urlparse
from typing import Protocol
from uuid import UUID, uuid4


class CommercialError(RuntimeError):
    """Raised when a commercial workflow transition is invalid."""


class OpportunityStatus(str, Enum):
    DISCOVERED = "DISCOVERED"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    QUALIFIED = "QUALIFIED"
    REJECTED = "REJECTED"


class ProposalStatus(str, Enum):
    DRAFT = "DRAFT"
    AWAITING_OWNER_APPROVAL = "AWAITING_OWNER_APPROVAL"
    APPROVED_FOR_SUBMISSION = "APPROVED_FOR_SUBMISSION"


@dataclass(frozen=True)
class CommercialOpportunity:
    title: str
    description: str
    source_name: str
    source_url: str
    budget_min: Decimal
    budget_max: Decimal
    currency: str
    required_capabilities: frozenset[str]
    evidence_refs: tuple[str, ...]
    discovered_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    deadline: datetime | None = None
    opportunity_id: UUID = field(default_factory=uuid4)
    status: OpportunityStatus = OpportunityStatus.DISCOVERED

    def __post_init__(self) -> None:
        if not self.title.strip() or not self.description.strip():
            raise ValueError("opportunity title and description are required")
        if not self.source_name.strip():
            raise ValueError("source_name is required")
        parsed = urlparse(self.source_url)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            raise ValueError("source_url must be an absolute HTTP(S) URL")
        if self.budget_min < 0 or self.budget_max < self.budget_min:
            raise ValueError("invalid opportunity budget range")
        if len(self.currency) != 3 or not self.currency.isalpha():
            raise ValueError("currency must be a three-letter code")
        if not self.required_capabilities:
            raise ValueError("required_capabilities cannot be empty")
        if not self.evidence_refs or any(not item.strip() for item in self.evidence_refs):
            raise ValueError("at least one evidence reference is required")
        if self.discovered_at.tzinfo is None:
            raise ValueError("discovered_at must be timezone-aware")
        if self.deadline is not None and self.deadline.tzinfo is None:
            raise ValueError("deadline must be timezone-aware")


@dataclass(frozen=True)
class CommercialAssessment:
    opportunity_id: UUID
    estimated_delivery_cost: Decimal
    platform_fee_rate: Decimal
    contingency_rate: Decimal
    win_probability: Decimal
    minimum_net_margin: Decimal
    terms_reviewed: bool
    eligibility_confirmed: bool
    assessed_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __post_init__(self) -> None:
        for name in (
            "platform_fee_rate",
            "contingency_rate",
            "win_probability",
            "minimum_net_margin",
        ):
            value = getattr(self, name)
            if value < 0 or value > 1:
                raise ValueError(f"{name} must be between 0 and 1")
        if self.estimated_delivery_cost < 0:
            raise ValueError("estimated_delivery_cost cannot be negative")
        if self.assessed_at.tzinfo is None:
            raise ValueError("assessed_at must be timezone-aware")


@dataclass(frozen=True)
class QualificationResult:
    opportunity_id: UUID
    status: OpportunityStatus
    conservative_revenue: Decimal
    estimated_total_cost: Decimal
    expected_net_profit: Decimal
    expected_net_margin: Decimal
    risk_adjusted_value: Decimal
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class ProposalDraft:
    opportunity_id: UUID
    scope: str
    acceptance_criteria: tuple[str, ...]
    delivery_plan: tuple[str, ...]
    quote_amount: Decimal
    currency: str
    proposal_id: UUID = field(default_factory=uuid4)
    status: ProposalStatus = ProposalStatus.DRAFT
    owner_approved_by: str | None = None
    owner_approved_at: datetime | None = None

    def __post_init__(self) -> None:
        if not self.scope.strip():
            raise ValueError("proposal scope is required")
        if not self.acceptance_criteria or not self.delivery_plan:
            raise ValueError("acceptance criteria and delivery plan are required")
        if self.quote_amount <= 0:
            raise ValueError("quote_amount must be positive")
        if len(self.currency) != 3:
            raise ValueError("currency must be a three-letter code")


class CommercialEvidenceGate(Protocol):
    """Validates that an opportunity's evidence was accepted by its owner."""

    def require_accepted(
        self, opportunity_id: UUID, evidence_refs: tuple[str, ...]
    ) -> None:
        ...


class CommercialEngine:
    """In-memory opportunity pipeline with conservative economics and approval gates."""

    def __init__(self, evidence_gate: CommercialEvidenceGate | None = None) -> None:
        self._evidence_gate = evidence_gate
        self._opportunities: dict[UUID, CommercialOpportunity] = {};

    def set_evidence_gate(self, evidence_gate: CommercialEvidenceGate | None) -> None:
        """Attach the fail-closed evidence gate used for future assessments."""
        self._evidence_gate = evidence_gate
        self._assessments: dict[UUID, CommercialAssessment] = {}
        self._results: dict[UUID, QualificationResult] = {}
        self._proposals: dict[UUID, ProposalDraft] = {}

    @property
    def opportunities(self) -> tuple[CommercialOpportunity, ...]:
        return tuple(self._opportunities.values())

    @property
    def proposals(self) -> tuple[ProposalDraft, ...]:
        return tuple(self._proposals.values())

    def add_opportunity(self, opportunity: CommercialOpportunity) -> None:
        if opportunity.opportunity_id in self._opportunities:
            raise CommercialError("opportunity already exists")
        self._opportunities[opportunity.opportunity_id] = opportunity

    def assess(
        self,
        assessment: CommercialAssessment,
        *,
        now: datetime | None = None,
    ) -> QualificationResult:
        opportunity = self._get_opportunity(assessment.opportunity_id)
        current_time = now or datetime.now(timezone.utc)
        if current_time.tzinfo is None:
            raise ValueError("now must be timezone-aware")

        revenue = opportunity.budget_min
        fee = revenue * assessment.platform_fee_rate
        contingency = assessment.estimated_delivery_cost * assessment.contingency_rate
        total_cost = assessment.estimated_delivery_cost + fee + contingency
        net_profit = revenue - total_cost
        net_margin = net_profit / revenue if revenue > 0 else Decimal("-1")
        risk_adjusted = net_profit * assessment.win_probability
        reasons: list[str] = []

        if self._evidence_gate is not None:
            try:
                self._evidence_gate.require_accepted(
                    opportunity.opportunity_id, opportunity.evidence_refs
                )
            except Exception:
                reasons.append("evidence_not_owner_accepted")

        if opportunity.deadline is not None and opportunity.deadline <= current_time:
            reasons.append("deadline_expired")
        if not assessment.terms_reviewed:
            reasons.append("terms_not_reviewed")
        if not assessment.eligibility_confirmed:
            reasons.append("eligibility_not_confirmed")
        if revenue <= 0:
            reasons.append("no_confirmed_budget_floor")
        if net_profit <= 0:
            reasons.append("non_positive_expected_net_profit")
        if net_margin < assessment.minimum_net_margin:
            reasons.append("net_margin_below_threshold")

        if reasons:
            status = (
                OpportunityStatus.REJECTED
                if "deadline_expired" in reasons
                or "non_positive_expected_net_profit" in reasons
                or "net_margin_below_threshold" in reasons
                else OpportunityStatus.NEEDS_REVIEW
            )
        else:
            status = OpportunityStatus.QUALIFIED

        result = QualificationResult(
            opportunity_id=opportunity.opportunity_id,
            status=status,
            conservative_revenue=revenue,
            estimated_total_cost=total_cost,
            expected_net_profit=net_profit,
            expected_net_margin=net_margin,
            risk_adjusted_value=risk_adjusted,
            reasons=tuple(reasons),
        )
        self._assessments[opportunity.opportunity_id] = assessment
        self._results[opportunity.opportunity_id] = result
        self._opportunities[opportunity.opportunity_id] = replace(
            opportunity, status=status
        )
        return result

    def draft_proposal(
        self,
        proposal: ProposalDraft,
    ) -> ProposalDraft:
        opportunity = self._get_opportunity(proposal.opportunity_id)
        result = self._results.get(proposal.opportunity_id)
        if result is None or result.status is not OpportunityStatus.QUALIFIED:
            raise CommercialError("only qualified opportunities can receive proposals")
        if proposal.currency.upper() != opportunity.currency.upper():
            raise CommercialError("proposal currency must match opportunity currency")
        if proposal.quote_amount < result.conservative_revenue:
            raise CommercialError("proposal quote cannot undercut the conservative budget floor")
        if proposal.proposal_id in self._proposals:
            raise CommercialError("proposal already exists")
        pending = replace(proposal, status=ProposalStatus.AWAITING_OWNER_APPROVAL)
        self._proposals[pending.proposal_id] = pending
        return pending

    def approve_proposal(
        self,
        proposal_id: UUID,
        owner_id: str,
        *,
        now: datetime | None = None,
    ) -> ProposalDraft:
        if not owner_id.strip():
            raise ValueError("owner_id is required")
        try:
            proposal = self._proposals[proposal_id]
        except KeyError as exc:
            raise CommercialError("unknown proposal") from exc
        if proposal.status is not ProposalStatus.AWAITING_OWNER_APPROVAL:
            raise CommercialError("proposal is not awaiting owner approval")
        approved_at = now or datetime.now(timezone.utc)
        if approved_at.tzinfo is None:
            raise ValueError("approval timestamp must be timezone-aware")
        approved = replace(
            proposal,
            status=ProposalStatus.APPROVED_FOR_SUBMISSION,
            owner_approved_by=owner_id,
            owner_approved_at=approved_at,
        )
        self._proposals[proposal_id] = approved
        return approved

    def to_snapshot(self) -> dict[str, object]:
        def dt(value):
            return value.isoformat() if value is not None else None

        return {
            "schema_version": 1,
            "opportunities": [
                {**{key: getattr(item, key) for key in (
                    "title", "description", "source_name", "source_url", "currency"
                )},
                 "opportunity_id": str(item.opportunity_id),
                 "budget_min": str(item.budget_min), "budget_max": str(item.budget_max),
                 "required_capabilities": sorted(item.required_capabilities),
                 "evidence_refs": list(item.evidence_refs),
                 "discovered_at": dt(item.discovered_at), "deadline": dt(item.deadline),
                 "status": item.status.value}
                for item in self._opportunities.values()
            ],
            "assessments": [
                {"opportunity_id": str(x.opportunity_id),
                 "estimated_delivery_cost": str(x.estimated_delivery_cost),
                 "platform_fee_rate": str(x.platform_fee_rate),
                 "contingency_rate": str(x.contingency_rate),
                 "win_probability": str(x.win_probability),
                 "minimum_net_margin": str(x.minimum_net_margin),
                 "terms_reviewed": x.terms_reviewed,
                 "eligibility_confirmed": x.eligibility_confirmed,
                 "assessed_at": dt(x.assessed_at)}
                for x in self._assessments.values()
            ],
            "results": [
                {"opportunity_id": str(x.opportunity_id), "status": x.status.value,
                 "conservative_revenue": str(x.conservative_revenue),
                 "estimated_total_cost": str(x.estimated_total_cost),
                 "expected_net_profit": str(x.expected_net_profit),
                 "expected_net_margin": str(x.expected_net_margin),
                 "risk_adjusted_value": str(x.risk_adjusted_value),
                 "reasons": list(x.reasons)}
                for x in self._results.values()
            ],
            "proposals": [
                {"proposal_id": str(x.proposal_id), "opportunity_id": str(x.opportunity_id),
                 "scope": x.scope, "acceptance_criteria": list(x.acceptance_criteria),
                 "delivery_plan": list(x.delivery_plan), "quote_amount": str(x.quote_amount),
                 "currency": x.currency, "status": x.status.value,
                 "owner_approved_by": x.owner_approved_by,
                 "owner_approved_at": dt(x.owner_approved_at)}
                for x in self._proposals.values()
            ],
        }

    @classmethod
    def from_snapshot(cls, payload: dict[str, object]) -> CommercialEngine:
        if payload.get("schema_version") != 1:
            raise ValueError("unsupported commercial snapshot schema")
        def dt(value):
            return datetime.fromisoformat(value) if value is not None else None
        engine = cls()
        for x in payload["opportunities"]:
            item = CommercialOpportunity(
                opportunity_id=UUID(x["opportunity_id"]), title=x["title"],
                description=x["description"], source_name=x["source_name"],
                source_url=x["source_url"], budget_min=Decimal(x["budget_min"]),
                budget_max=Decimal(x["budget_max"]), currency=x["currency"],
                required_capabilities=frozenset(x["required_capabilities"]),
                evidence_refs=tuple(x["evidence_refs"]),
                discovered_at=dt(x["discovered_at"]), deadline=dt(x["deadline"]),
                status=OpportunityStatus(x["status"]),
            )
            engine.add_opportunity(item)
        for x in payload["assessments"]:
            item = CommercialAssessment(
                opportunity_id=UUID(x["opportunity_id"]),
                estimated_delivery_cost=Decimal(x["estimated_delivery_cost"]),
                platform_fee_rate=Decimal(x["platform_fee_rate"]),
                contingency_rate=Decimal(x["contingency_rate"]),
                win_probability=Decimal(x["win_probability"]),
                minimum_net_margin=Decimal(x["minimum_net_margin"]),
                terms_reviewed=x["terms_reviewed"],
                eligibility_confirmed=x["eligibility_confirmed"],
                assessed_at=dt(x["assessed_at"]),
            )
            engine._assessments[item.opportunity_id] = item
        for x in payload["results"]:
            item = QualificationResult(
                opportunity_id=UUID(x["opportunity_id"]),
                status=OpportunityStatus(x["status"]),
                conservative_revenue=Decimal(x["conservative_revenue"]),
                estimated_total_cost=Decimal(x["estimated_total_cost"]),
                expected_net_profit=Decimal(x["expected_net_profit"]),
                expected_net_margin=Decimal(x["expected_net_margin"]),
                risk_adjusted_value=Decimal(x["risk_adjusted_value"]),
                reasons=tuple(x["reasons"]),
            )
            engine._results[item.opportunity_id] = item
        for x in payload["proposals"]:
            item = ProposalDraft(
                proposal_id=UUID(x["proposal_id"]), opportunity_id=UUID(x["opportunity_id"]),
                scope=x["scope"], acceptance_criteria=tuple(x["acceptance_criteria"]),
                delivery_plan=tuple(x["delivery_plan"]), quote_amount=Decimal(x["quote_amount"]),
                currency=x["currency"], status=ProposalStatus(x["status"]),
                owner_approved_by=x["owner_approved_by"],
                owner_approved_at=dt(x["owner_approved_at"]),
            )
            engine._proposals[item.proposal_id] = item
        if set(engine._assessments) != set(engine._results):
            raise ValueError("commercial assessment/result references are inconsistent")
        if any(key not in engine._opportunities for key in engine._assessments):
            raise ValueError("assessment references unknown opportunity")
        if any(x.opportunity_id not in engine._opportunities for x in engine._proposals.values()):
            raise ValueError("proposal references unknown opportunity")
        return engine

    def _get_opportunity(self, opportunity_id: UUID) -> CommercialOpportunity:
        try:
            return self._opportunities[opportunity_id]
        except KeyError as exc:
            raise CommercialError("unknown opportunity") from exc
