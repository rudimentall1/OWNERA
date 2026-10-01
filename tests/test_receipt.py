from decimal import Decimal

from ownera.authorization import AuthorizationIssuer
from ownera.domain import Decision, Money, PaymentIntent
from ownera.firewall import AuthorizationDecision
from ownera.receipt import ExecutionReceipt


def test_committed_receipt_preserves_authorization_binding() -> None:
    intent = PaymentIntent(
        amount=Money(Decimal("25"), "EUR"),
        destination="alice",
        purpose="bill",
        idempotency_key="receipt-1",
    )
    verdict = AuthorizationDecision(
        intent_id=intent.id,
        decision=Decision.ALLOW,
        reasons=("policy_satisfied",),
        correlation_id=__import__("uuid").uuid4(),
    )
    auth = AuthorizationIssuer().issue(intent, verdict, policy_version="v2")
    receipt = ExecutionReceipt.committed(
        auth,
        amount=intent.amount.amount,
        currency=intent.amount.currency,
        destination=intent.destination,
    )

    assert receipt.authorization_id == auth.id
    assert receipt.intent_id == intent.id
    assert receipt.correlation_id == auth.correlation_id
    assert receipt.policy_version == "v2"
    assert receipt.status == "COMMITTED"
