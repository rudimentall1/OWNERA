from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

from ownera.authorization import AuthorizationIssuer
from ownera.domain import Decision, Money, PaymentIntent
from ownera.evidence import ExecutionEvidence
from ownera.financial_action import FinancialAction
from ownera.firewall import AuthorizationDecision
from ownera.receipt import ExecutionReceipt


def _execution():
    intent = PaymentIntent(
        amount=Money(Decimal("25.000000000000000001"), "EUR"),
        destination="alice",
        purpose="bill",
        idempotency_key="evidence-1",
    )
    action = FinancialAction(
        intent_id=intent.id,
        agent_id="owner-agent",
        action_type="payment",
        destination=intent.destination,
        amount=intent.amount.amount,
        currency=intent.amount.currency,
        purpose=intent.purpose,
        idempotency_key=intent.idempotency_key,
    )
    verdict = AuthorizationDecision(
        intent_id=intent.id,
        decision=Decision.ALLOW,
        reasons=(),
        correlation_id=uuid4(),
    )
    authorization = AuthorizationIssuer().issue(
        intent,
        verdict,
        policy_version="v7",
        now=datetime(2026, 10, 1, tzinfo=timezone.utc),
    )
    receipt = ExecutionReceipt.committed(
        authorization,
        amount=intent.amount.amount,
        currency=intent.amount.currency,
        destination=intent.destination,
        executed_at=datetime(2026, 10, 1, 0, 1, tzinfo=timezone.utc),
    )
    return action, authorization, receipt


def test_evidence_is_deterministic_and_integrity_verifiable():
    action, authorization, receipt = _execution()
    evidence = ExecutionEvidence.from_execution(
        action, authorization, receipt, evidence_id=uuid4()
    )

    assert evidence.verify_integrity()
    assert evidence.manifest()["amount"] == "25.000000000000000001"
    assert evidence.manifest()["financial_action_sha256"] == action.digest()


def test_evidence_detects_tampering():
    action, authorization, receipt = _execution()
    evidence = ExecutionEvidence.from_execution(
        action, authorization, receipt, evidence_id=uuid4()
    )

    manifest = evidence.manifest()
    manifest["amount"] = "2500000"

    assert manifest["evidence_sha256"] != __import__("hashlib").sha256(
        __import__("json").dumps(
            {k: v for k, v in manifest.items() if k != "evidence_sha256"},
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode()
    ).hexdigest()


def test_evidence_rejects_mismatched_execution():
    action, authorization, receipt = _execution()
    tampered = ExecutionReceipt.committed(
        authorization,
        amount=Decimal("26"),
        currency=receipt.currency,
        destination=receipt.destination,
        executed_at=receipt.executed_at,
    )

    try:
        ExecutionEvidence.from_execution(
            action, authorization, tampered, evidence_id=uuid4()
        )
    except ValueError as exc:
        assert "amount" in str(exc)
    else:
        raise AssertionError("mismatched execution must be rejected")
