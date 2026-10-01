from decimal import Decimal

from ownera.domain import Decision
from ownera.firewall import FirewallConfig, TransactionFirewall
from ownera.sandbox import SandboxTreasury
from ownera.security import SpendingPolicy


def make_treasury() -> SandboxTreasury:
    policy = SpendingPolicy(max_single_payment=Decimal("500"), currency="EUR")
    firewall = TransactionFirewall(FirewallConfig(policy=policy))
    return SandboxTreasury(firewall, balance=Decimal("1000"))


def test_sandbox_committed_payment_has_authorization_and_receipt() -> None:
    result = make_treasury().propose_payment(
        Decimal("100"),
        "alice",
        "invoice",
        idempotency_key="sandbox-auth-1",
    )

    assert result.decision == Decision.ALLOW
    assert result.committed is True
    assert result.authorization is not None
    assert result.receipt is not None
    assert result.receipt.authorization_id == result.authorization.id
    assert result.receipt.intent_id == result.intent.id
    assert result.receipt.policy_version == "v0"


def test_sandbox_does_not_mint_authorization_when_balance_is_insufficient() -> None:
    treasury = make_treasury()
    treasury.balance = Decimal("50")

    result = treasury.propose_payment(
        Decimal("100"),
        "alice",
        "invoice",
        idempotency_key="sandbox-auth-2",
    )

    assert result.decision == Decision.REVIEW
    assert result.committed is False
    assert result.authorization is None
    assert result.receipt is None
