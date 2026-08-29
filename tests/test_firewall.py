from decimal import Decimal

from ownera.domain import Decision
from ownera.firewall import FirewallConfig, TransactionFirewall
from ownera.security import SpendingPolicy
from ownera.sandbox import SandboxTreasury


def test_firewall_allows_small_payment() -> None:
    firewall = TransactionFirewall(FirewallConfig(SpendingPolicy(Decimal("100"), "EUR")))
    treasury = SandboxTreasury(firewall, balance=Decimal("500"))

    result = treasury.propose_payment(Decimal("25"), "alice", "subscription")

    assert result.decision == Decision.ALLOW
    assert result.committed is True
    assert treasury.balance == Decimal("475")


def test_firewall_reviews_over_limit_before_commit() -> None:
    firewall = TransactionFirewall(FirewallConfig(SpendingPolicy(Decimal("100"), "EUR")))
    treasury = SandboxTreasury(firewall, balance=Decimal("500"))

    result = treasury.propose_payment(Decimal("101"), "alice", "payment")

    assert result.decision == Decision.REVIEW
    assert result.committed is False
    assert treasury.balance == Decimal("500")


def test_sandbox_never_commits_when_balance_is_insufficient() -> None:
    firewall = TransactionFirewall(FirewallConfig(SpendingPolicy(Decimal("1000"), "EUR")))
    treasury = SandboxTreasury(firewall, balance=Decimal("10"))

    result = treasury.propose_payment(Decimal("50"), "alice", "payment")

    assert result.decision == Decision.REVIEW
    assert result.committed is False
    assert treasury.balance == Decimal("10")
