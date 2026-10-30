"""Owner-approved customer order handoff into the deterministic workforce queue.

This bridge creates bounded tasks only from a customer-accepted proposal that
was approved by the owner. It does not execute tasks or submit deliverables.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID, uuid4

from ownera.acceptance import (
    AcceptanceVerificationError,
    CustomerAcceptanceAttestation,
    TrustedCustomerKeyRegistry,
    verify_customer_acceptance,
)
from ownera.commercial import ProposalDraft, ProposalStatus
from ownera.workforce import WorkforceEngine, WorkTask


class OrderHandoffError(RuntimeError):
    """Raised when an order cannot safely enter the workforce queue."""


@dataclass(frozen=True)
class CustomerOrder:
    proposal_id: UUID
    customer_id: str
    accepted_amount: Decimal
    currency: str
    customer_acceptance_ref: str
    accepted_scope: str
    accepted_acceptance_criteria: tuple[str, ...]
    customer_accepted_at: datetime
    owner_approved_by: str
    owner_approved_at: datetime
    execution_budget_limit: Decimal
    order_id: UUID = field(default_factory=uuid4)
    acceptance_attestation: CustomerAcceptanceAttestation | None = None

    def __post_init__(self) -> None:
        if not self.customer_id.strip():
            raise ValueError("customer_id is required")
        if self.accepted_amount <= 0:
            raise ValueError("accepted_amount must be positive")
        if len(self.currency) != 3 or not self.currency.isalpha():
            raise ValueError("currency must be a three-letter code")
        if not self.customer_acceptance_ref.strip():
            raise ValueError("customer acceptance evidence is required")
        if not self.accepted_scope.strip() or not self.accepted_acceptance_criteria:
            raise ValueError("customer-accepted scope and acceptance criteria are required")
        if not self.owner_approved_by.strip():
            raise ValueError("owner approval is required")
        if self.execution_budget_limit < 0:
            raise ValueError("execution_budget_limit cannot be negative")
        if self.customer_accepted_at.tzinfo is None:
            raise ValueError("customer_accepted_at must be timezone-aware")
        if self.owner_approved_at.tzinfo is None:
            raise ValueError("owner_approved_at must be timezone-aware")
        if self.owner_approved_at > self.customer_accepted_at:
            raise ValueError("owner approval must precede customer acceptance")


@dataclass(frozen=True)
class TaskSpec:
    title: str
    description: str
    required_capabilities: frozenset[str]
    budget_limit: Decimal
    acceptance_criteria: tuple[str, ...]
    depends_on: tuple[int, ...] = ()

    def __post_init__(self) -> None:
        if not self.title.strip() or not self.description.strip():
            raise ValueError("task title and description are required")
        if not self.required_capabilities:
            raise ValueError("task capabilities are required")
        if self.budget_limit < 0:
            raise ValueError("task budget cannot be negative")
        if not self.acceptance_criteria or any(
            not criterion.strip() for criterion in self.acceptance_criteria
        ):
            raise ValueError("task acceptance criteria are required")
        if any(index < 0 for index in self.depends_on):
            raise ValueError("dependency indexes cannot be negative")


@dataclass(frozen=True)
class OrderHandoff:
    order_id: UUID
    proposal_id: UUID
    task_ids: tuple[UUID, ...]
    converted_at: datetime
    evidence_digest: str


class OrderToWorkforceBridge:
    """Validates customer/owner approvals and converts an order exactly once."""

    def __init__(
        self, *, trusted_keys: TrustedCustomerKeyRegistry | None = None,
        require_verified_acceptance: bool = False,
    ) -> None:
        self._handoffs: dict[UUID, OrderHandoff] = {}
        self._trusted_keys = trusted_keys
        self._require_verified_acceptance = require_verified_acceptance

    @property
    def handoffs(self) -> tuple[OrderHandoff, ...]:
        return tuple(self._handoffs.values())

    def convert(
        self,
        order: CustomerOrder,
        proposal: ProposalDraft,
        task_specs: tuple[TaskSpec, ...],
        workforce: WorkforceEngine,
        *,
        now: datetime | None = None,
    ) -> OrderHandoff:
        if order.order_id in self._handoffs:
            raise OrderHandoffError("order has already been converted")
        acceptance_verification = None
        if self._trusted_keys is not None and order.acceptance_attestation is not None:
            try:
                acceptance_verification = verify_customer_acceptance(order, self._trusted_keys)
            except AcceptanceVerificationError as exc:
                raise OrderHandoffError(str(exc)) from exc
        if self._require_verified_acceptance and acceptance_verification is None:
            raise OrderHandoffError("verified customer acceptance is required")
        if proposal.proposal_id != order.proposal_id:
            raise OrderHandoffError("order does not reference this proposal")
        if proposal.status is not ProposalStatus.APPROVED_FOR_SUBMISSION:
            raise OrderHandoffError("proposal is not approved by the owner")
        if not proposal.owner_approved_by or proposal.owner_approved_at is None:
            raise OrderHandoffError("proposal owner approval evidence is missing")
        if order.currency.upper() != proposal.currency.upper():
            raise OrderHandoffError("order currency does not match proposal")
        if order.accepted_amount != proposal.quote_amount:
            raise OrderHandoffError("customer acceptance amount differs from approved quote")
        if order.accepted_scope != proposal.scope:
            raise OrderHandoffError("customer-accepted scope differs from approved proposal")
        if order.accepted_acceptance_criteria != proposal.acceptance_criteria:
            raise OrderHandoffError(
                "customer-accepted criteria differ from approved proposal"
            )
        if order.owner_approved_by != proposal.owner_approved_by:
            raise OrderHandoffError("order owner approver does not match proposal approval")
        if order.owner_approved_at < proposal.owner_approved_at:
            raise OrderHandoffError("order approval predates proposal approval")
        if not task_specs:
            raise OrderHandoffError("at least one task is required")
        if any(spec.budget_limit < 0 for spec in task_specs):
            raise OrderHandoffError("task budget cannot be negative")

        total_budget = sum((spec.budget_limit for spec in task_specs), Decimal("0"))
        if total_budget > order.execution_budget_limit:
            raise OrderHandoffError("task budgets exceed the approved execution budget")
        if order.execution_budget_limit > order.accepted_amount:
            raise OrderHandoffError("execution budget cannot exceed accepted order amount")

        for index, spec in enumerate(task_specs):
            if any(dependency >= index for dependency in spec.depends_on):
                raise OrderHandoffError(
                    "dependencies must reference earlier tasks in the task plan"
                )

        tasks: list[WorkTask] = []
        for index, spec in enumerate(task_specs):
            dependencies = tuple(tasks[dependency].task_id for dependency in spec.depends_on)
            tasks.append(
                WorkTask(
                    title=spec.title,
                    description=spec.description,
                    required_capabilities=spec.required_capabilities,
                    budget_limit=spec.budget_limit,
                    currency=order.currency.upper(),
                    acceptance_criteria=spec.acceptance_criteria,
                    dependencies=dependencies,
                )
            )

        converted_at = now or datetime.now(timezone.utc)
        if converted_at.tzinfo is None:
            raise ValueError("conversion timestamp must be timezone-aware")

        acceptance_evidence = {
            "schema_version": 1,
            "order_id": str(order.order_id),
            "proposal_id": str(order.proposal_id),
            "customer_id": order.customer_id,
            "customer_acceptance_reference": order.customer_acceptance_ref,
            "accepted_amount": str(order.accepted_amount),
            "currency": order.currency.upper(),
            "accepted_scope": order.accepted_scope,
            "accepted_acceptance_criteria": list(order.accepted_acceptance_criteria),
            "customer_accepted_at": order.customer_accepted_at.isoformat(),
            "owner_approved_by": order.owner_approved_by,
            "owner_approved_at": order.owner_approved_at.isoformat(),
            "execution_budget_limit": str(order.execution_budget_limit),
            "customer_acceptance_attestation": (
                {
                    "key_id": order.acceptance_attestation.key_id,
                    "signature_b64": order.acceptance_attestation.signature_b64,
                    "nonce": order.acceptance_attestation.nonce,
                }
                if order.acceptance_attestation is not None else None
            ),
            "acceptance_verification": (
                {"status": acceptance_verification.status, "key_id": acceptance_verification.key_id,
                 "attestation_digest": acceptance_verification.attestation_digest,
                 "reason": acceptance_verification.reason}
                if acceptance_verification is not None else
                {"status": "UNVERIFIED", "key_id": None, "attestation_digest": None,
                 "reason": "no trusted signature configured"}
            ),
        }

        evidence_json = json.dumps(
            acceptance_evidence, sort_keys=True, separators=(",", ":"),
            ensure_ascii=False, allow_nan=False,
        )
        evidence_digest = hashlib.sha256(evidence_json.encode("utf-8")).hexdigest()

        # The plan digest excludes generated task IDs so a retry after a crash
        # can resolve to the original committed task graph.
        plan_payload = [
            {
                "title": spec.title,
                "description": spec.description,
                "required_capabilities": sorted(spec.required_capabilities),
                "budget_limit": str(spec.budget_limit),
                "currency": order.currency.upper(),
                "acceptance_criteria": list(spec.acceptance_criteria),
                "depends_on": list(spec.depends_on),
            }
            for spec in task_specs
        ]
        plan_digest = hashlib.sha256(
            json.dumps(
                plan_payload,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
            ).encode("utf-8")
        ).hexdigest()

        # PersistentWorkforce commits the task graph and unique order record in
        # the same SQLite transaction. The in-memory engine uses atomic batching.
        try:
            if hasattr(workforce, "add_order_tasks"):
                persisted = workforce.add_order_tasks(
                    tuple(tasks),
                    order_id=order.order_id,
                    proposal_id=proposal.proposal_id,
                    converted_at=converted_at.isoformat(),
                    plan_digest=plan_digest,
                    acceptance_evidence=acceptance_evidence,
                )
                handoff = OrderHandoff(
                    order_id=persisted.order_id,
                    proposal_id=persisted.proposal_id,
                    task_ids=persisted.task_ids,
                    converted_at=datetime.fromisoformat(persisted.converted_at),
                    evidence_digest=persisted.evidence_digest,
                )
            else:
                workforce.add_tasks(tuple(tasks))
                handoff = OrderHandoff(
                    order_id=order.order_id,
                    proposal_id=proposal.proposal_id,
                    task_ids=tuple(task.task_id for task in tasks),
                    converted_at=converted_at,
                    evidence_digest=evidence_digest,
                )
        except Exception as exc:
            raise OrderHandoffError("task graph registration failed") from exc
        self._handoffs[order.order_id] = handoff
        return handoff
