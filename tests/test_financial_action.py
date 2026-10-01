from decimal import Decimal
from uuid import uuid4

from ownera.financial_action import FinancialAction


def test_financial_action_canonicalizes_decimal_exactly() -> None:
    action = FinancialAction(
        intent_id=uuid4(),
        agent_id="ownera-financial-agent",
        action_type="payment",
        destination="alice",
        amount=Decimal("0.1000000000000000001"),
        currency="EUR",
        purpose="test",
        idempotency_key="payment-1",
    )

    payload = action.canonical_payload()

    assert payload["amount"] == "0.1000000000000000001"
    assert len(action.digest()) == 64


def test_financial_action_digest_changes_when_amount_changes() -> None:
    intent_id = uuid4()
    base = FinancialAction(
        intent_id=intent_id,
        agent_id="ownera-financial-agent",
        action_type="payment",
        destination="alice",
        amount=Decimal("10.00"),
        currency="EUR",
        purpose="test",
        idempotency_key="payment-1",
    )
    changed = FinancialAction(
        intent_id=intent_id,
        agent_id="ownera-financial-agent",
        action_type="payment",
        destination="alice",
        amount=Decimal("10.01"),
        currency="EUR",
        purpose="test",
        idempotency_key="payment-1",
    )

    assert base.digest() != changed.digest()
