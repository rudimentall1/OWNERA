from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

import pytest

from ownera.commercial import ProposalDraft, ProposalStatus
from ownera.order_handoff import (
    CustomerOrder,
    OrderHandoffError,
    OrderToWorkforceBridge,
    TaskSpec,
)
from ownera.workforce import TaskStatus, WorkerProfile, WorkforceEngine


def _proposal(status=ProposalStatus.APPROVED_FOR_SUBMISSION):
    return ProposalDraft(
        opportunity_id=uuid4(),
        scope="Build and test a bounded API integration.",
        acceptance_criteria=("API works", "Tests pass"),
        delivery_plan=("Implement", "Review", "Handover"),
        quote_amount=Decimal("1000"),
        currency="EUR",
        status=status,
        owner_approved_by="owner-1",
        owner_approved_at=datetime.now(timezone.utc) - timedelta(hours=2),
    )


def _order(proposal, **overrides):
    values = {
        "proposal_id": proposal.proposal_id,
        "customer_id": "customer-42",
        "accepted_amount": Decimal("1000"),
        "currency": "EUR",
        "customer_acceptance_ref": "contract:sha256:abc123",
        "accepted_scope": proposal.scope,
        "accepted_acceptance_criteria": proposal.acceptance_criteria,
        "customer_accepted_at": datetime.now(timezone.utc) - timedelta(hours=1),
        "owner_approved_by": "owner-1",
        "owner_approved_at": datetime.now(timezone.utc) - timedelta(hours=1, minutes=30),
        "execution_budget_limit": Decimal("600"),
    }
    values.update(overrides)
    return CustomerOrder(**values)


def _specs():
    return (
        TaskSpec(
            title="Implement API",
            description="Build the agreed API endpoint.",
            required_capabilities=frozenset({"python", "fastapi"}),
            budget_limit=Decimal("400"),
            acceptance_criteria=("Endpoint works", "Tests pass"),
        ),
        TaskSpec(
            title="Independent QA",
            description="Review the implementation and test evidence.",
            required_capabilities=frozenset({"quality.review"}),
            budget_limit=Decimal("200"),
            acceptance_criteria=("Review findings recorded",),
            depends_on=(0,),
        ),
    )


def _workforce():
    return WorkforceEngine(
        (
            WorkerProfile("backend", "backend", frozenset({"python", "fastapi"})),
            WorkerProfile("qa", "qa", frozenset({"quality.review"})),
        )
    )


def test_customer_accepted_owner_approved_order_creates_bounded_task_graph():
    proposal = _proposal()
    order = _order(proposal)
    workforce = _workforce()
    bridge = OrderToWorkforceBridge()

    handoff = bridge.convert(order, proposal, _specs(), workforce)

    assert len(handoff.task_ids) == 2
    first, second = workforce.tasks
    assert first.status is TaskStatus.PLANNED
    assert second.dependencies == (first.task_id,)
    assert sum((task.budget_limit for task in workforce.tasks), Decimal("0")) == Decimal("600")


def test_order_conversion_is_idempotently_blocked():
    proposal = _proposal()
    order = _order(proposal)
    bridge = OrderToWorkforceBridge()
    workforce = _workforce()
    bridge.convert(order, proposal, _specs(), workforce)

    with pytest.raises(OrderHandoffError, match="already been converted"):
        bridge.convert(order, proposal, _specs(), workforce)


def test_unapproved_proposal_cannot_be_converted():
    proposal = _proposal(ProposalStatus.AWAITING_OWNER_APPROVAL)
    with pytest.raises(OrderHandoffError, match="not approved"):
        OrderToWorkforceBridge().convert(
            _order(proposal), proposal, _specs(), _workforce()
        )


def test_customer_amount_must_match_approved_quote():
    proposal = _proposal()
    order = _order(proposal, accepted_amount=Decimal("900"))

    with pytest.raises(OrderHandoffError, match="differs from approved quote"):
        OrderToWorkforceBridge().convert(order, proposal, _specs(), _workforce())


def test_task_budgets_must_fit_execution_budget():
    proposal = _proposal()
    order = _order(proposal, execution_budget_limit=Decimal("500"))

    with pytest.raises(OrderHandoffError, match="exceed the approved execution budget"):
        OrderToWorkforceBridge().convert(order, proposal, _specs(), _workforce())


def test_task_plan_dependencies_must_be_topologically_ordered():
    proposal = _proposal()
    invalid = (
        TaskSpec(
            title="First task",
            description="Should not depend on a future task.",
            required_capabilities=frozenset({"python"}),
            budget_limit=Decimal("100"),
            acceptance_criteria=("Done",),
            depends_on=(1,),
        ),
        TaskSpec(
            title="Second task",
            description="Second.",
            required_capabilities=frozenset({"python"}),
            budget_limit=Decimal("100"),
            acceptance_criteria=("Done",),
        ),
    )

    with pytest.raises(OrderHandoffError, match="earlier tasks"):
        OrderToWorkforceBridge().convert(
            _order(proposal), proposal, invalid, _workforce()
        )


def test_customer_accepted_scope_must_match_proposal():
    proposal = _proposal()
    order = _order(proposal, accepted_scope="A materially different scope")

    with pytest.raises(OrderHandoffError, match="scope differs"):
        OrderToWorkforceBridge().convert(
            order, proposal, _specs(), _workforce()
        )


def test_customer_accepted_criteria_must_match_proposal():
    proposal = _proposal()
    order = _order(proposal, accepted_acceptance_criteria=("Only API works",))

    with pytest.raises(OrderHandoffError, match="criteria differ"):
        OrderToWorkforceBridge().convert(
            order, proposal, _specs(), _workforce()
        )



def test_order_handoff_persists_complete_task_graph_in_one_workforce_snapshot(tmp_path):
    from ownera.persistent_workforce import PersistentWorkforce

    database = tmp_path / "ownera.sqlite3"
    workforce = PersistentWorkforce(database)
    proposal = _proposal()
    order = _order(proposal)
    bridge = OrderToWorkforceBridge()

    handoff = bridge.convert(order, proposal, _specs(), workforce)
    restored = PersistentWorkforce(database)

    assert len(handoff.task_ids) == 2
    assert tuple(task.task_id for task in restored.tasks) == handoff.task_ids
    assert restored.tasks[1].dependencies == (restored.tasks[0].task_id,)
    assert restored.version == workforce.version



def test_persistent_order_handoff_is_idempotent_across_bridge_restart(tmp_path):
    from ownera.persistent_workforce import PersistentWorkforce

    database = tmp_path / "ownera.sqlite3"
    proposal = _proposal()
    order = _order(proposal)
    first_bridge = OrderToWorkforceBridge()
    first_workforce = PersistentWorkforce(database)
    first = first_bridge.convert(order, proposal, _specs(), first_workforce)

    second_bridge = OrderToWorkforceBridge()
    second_workforce = PersistentWorkforce(database)
    replay = second_bridge.convert(order, proposal, _specs(), second_workforce)

    assert replay == first
    assert tuple(task.task_id for task in second_workforce.tasks) == first.task_ids
    assert second_workforce.version == first_workforce.version


def test_persistent_order_id_cannot_be_reused_for_different_task_plan(tmp_path):
    from ownera.persistent_workforce import PersistentWorkforce

    database = tmp_path / "ownera.sqlite3"
    proposal = _proposal()
    order = _order(proposal)
    workforce = PersistentWorkforce(database)
    OrderToWorkforceBridge().convert(order, proposal, _specs(), workforce)

    changed_specs = (
        TaskSpec(
            title="Different implementation",
            description="A materially different task plan.",
            required_capabilities=frozenset({"python", "fastapi"}),
            budget_limit=Decimal("400"),
            acceptance_criteria=("Different result",),
        ),
    )
    restarted = PersistentWorkforce(database)
    with pytest.raises(OrderHandoffError, match="registration failed"):
        OrderToWorkforceBridge().convert(order, proposal, changed_specs, restarted)

    assert len(restarted.tasks) == 2
