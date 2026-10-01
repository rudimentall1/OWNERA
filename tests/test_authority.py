from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from ownera.authority import LocalAuthorityAdapter
from ownera.authorization import AuthorizationError
from ownera.domain import Decision, Money, PaymentIntent
from ownera.firewall import AuthorizationDecision


def make_intent() -> PaymentIntent:
    return PaymentIntent(
        amount=Money(Decimal("10"), "EUR"),
        destination="alice",
        purpose="sandbox",
        idempotency_key="authority-test-1",
    )


def make_verdict(intent: PaymentIntent, decision: Decision = Decision.ALLOW) -> AuthorizationDecision:
    return AuthorizationDecision(
        intent_id=intent.id,
        decision=decision,
        reasons=(),
        correlation_id=intent.id,
    )


def test_local_adapter_issues_and_consumes_allow() -> None:
    adapter = LocalAuthorityAdapter.create()
    intent = make_intent()
    authorization = adapter.issue(intent, make_verdict(intent), policy_version="v1")

    adapter.consume(authorization, intent)


def test_local_adapter_does_not_issue_review() -> None:
    adapter = LocalAuthorityAdapter.create()
    intent = make_intent()

    with pytest.raises(AuthorizationError, match="only ALLOW"):
        adapter.issue(intent, make_verdict(intent, Decision.REVIEW), policy_version="v1")


def test_local_adapter_consumes_authorization_once() -> None:
    adapter = LocalAuthorityAdapter.create()
    intent = make_intent()
    authorization = adapter.issue(intent, make_verdict(intent), policy_version="v1")

    adapter.consume(authorization, intent)

    with pytest.raises(AuthorizationError, match="already consumed"):
        adapter.consume(authorization, intent)


def test_local_adapter_rejects_expired_authorization() -> None:
    adapter = LocalAuthorityAdapter.create(ttl_seconds=1)
    intent = make_intent()
    issued_at = datetime.now(timezone.utc)

    authorization = adapter.issue(
        intent,
        make_verdict(intent),
        policy_version="v1",
        now=issued_at,
    )

    with pytest.raises(AuthorizationError, match="expired"):
        adapter.consume(
            authorization,
            intent,
            now=issued_at + timedelta(seconds=2),
        )
