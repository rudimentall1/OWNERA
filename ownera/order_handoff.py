"""Owner-approved customer order handoff into the deterministic workforce queue.

This bridge creates bounded tasks only from a customer-accepted proposal that
was approved by the owner. It does not execute tasks or submit deliverables.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID, uuid4

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


class OrderToWorkforceBridge:
    """Validates customer/owner approvals and converts an order exactly once."""

    def __init__(self) -> None:
        self._handoffs: dict[UUID, OrderHandoff] = {}

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

        # All order and task-plan validations run before mutating the workforce.
        for task in tasks:
            workforce.add_task(task)
        handoff = OrderHandoff(
            order_id=order.order_id,
            proposal_id=proposal.proposal_id,
            task_ids=tuple(task.task_id for task in tasks),
            converted_at=converted_at,
        )
        self._handoffs[order.order_id] = handoff
        return handoff
