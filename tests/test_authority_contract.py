from decimal import Decimal
from uuid import uuid4

import pytest

from ownera.authority_contract import (
    AuthorityArtifact,
    require_action_binding,
    require_allow,
)
from ownera.domain import Decision
from ownera.financial_action import FinancialAction


def _action(amount: str = "10.00") -> FinancialAction:
    return FinancialAction(
        intent_id=uuid4(),
        agent_id="agent-1",
        action_type="payment",
        destination="merchant",
        amount=Decimal(amount),
        currency="EUR",
        purpose="invoice",
        idempotency_key="invoice-1",
    )


def test_authority_artifact_must_bind_to_sha256() -> None:
    action = _action()
    artifact = AuthorityArtifact(
        provider="verigate",
        action_digest=action.digest(),
        decision=Decision.ALLOW,
        artifact={"authorization_id": "auth-1"},
    )

    require_action_binding(artifact, action)
    require_allow(artifact)


def test_authority_binding_rejects_changed_amount() -> None:
    action = _action("10.00")
    changed = _action("10.01")
    artifact = AuthorityArtifact(
        provider="verigate",
        action_digest=action.digest(),
        decision=Decision.ALLOW,
        artifact={},
    )

    with pytest.raises(PermissionError, match="exact financial action"):
        require_action_binding(artifact, changed)


def test_non_allow_artifact_cannot_execute() -> None:
    action = _action()
    artifact = AuthorityArtifact(
        provider="verigate",
        action_digest=action.digest(),
        decision=Decision.REVIEW,
        artifact={},
    )

    with pytest.raises(PermissionError, match="did not grant"):
        require_allow(artifact)


def test_authority_artifact_rejects_invalid_digest() -> None:
    with pytest.raises(ValueError, match="lowercase hexadecimal"):
        AuthorityArtifact(
            provider="verigate",
            action_digest="A" * 64,
            decision=Decision.ALLOW,
            artifact={},
        )
