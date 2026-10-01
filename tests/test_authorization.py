from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from ownera.authorization import AuthorizationError, AuthorizationIssuer
from ownera.domain import Decision, Money, PaymentIntent
from ownera.firewall import AuthorizationDecision


def make_intent() -> PaymentIntent:
    return PaymentIntent(
        amount=Money(Decimal("25"), "EUR"),
        destination="alice",
        purpose="bill",
        idempotency_key="auth-1",
    )


def allow_verdict(intent: PaymentIntent) -> AuthorizationDecision:
    return AuthorizationDecision(
        intent_id=intent.id,
        decision=Decision.ALLOW,
        reasons=("policy_satisfied",),
        correlation_id=__import__("uuid").uuid4(),
    )


def test_only_allow_can_issue_authorization() -> None:
    intent = make_intent()
    issuer = AuthorizationIssuer()
    denied = AuthorizationDecision(intent.id, Decision.DENY, ("blocked",), __import__("uuid").uuid4())
    with pytest.raises(AuthorizationError):
        issuer.issue(intent, denied, policy_version="v1")


def test_authorization_is_bound_and_one_shot() -> None:
    intent = make_intent()
    issuer = AuthorizationIssuer()
    auth = issuer.issue(intent, allow_verdict(intent), policy_version="v1")
    issuer.consume(auth, intent)
    with pytest.raises(AuthorizationError, match="already consumed"):
        issuer.consume(auth, intent)


def test_authorization_expires() -> None:
    intent = make_intent()
    issuer = AuthorizationIssuer(ttl_seconds=60)
    issued = datetime(2026, 10, 1, tzinfo=timezone.utc)
    auth = issuer.issue(intent, allow_verdict(intent), policy_version="v1", now=issued)
    with pytest.raises(AuthorizationError, match="expired"):
        issuer.consume(auth, intent, now=issued + timedelta(seconds=60))


def test_authorization_rejects_wrong_intent() -> None:
    intent = make_intent()
    other = PaymentIntent(
        amount=Money(Decimal("25"), "EUR"),
        destination="mallory",
        purpose="bill",
        idempotency_key="auth-2",
    )
    issuer = AuthorizationIssuer()
    auth = issuer.issue(intent, allow_verdict(intent), policy_version="v1")
    with pytest.raises(AuthorizationError, match="intent mismatch"):
        issuer.consume(auth, other)
