from decimal import Decimal

from ownera.domain import Decision
from ownera.firewall import FirewallConfig, TransactionFirewall
from ownera.sandbox import SandboxTreasury
from ownera.security import SpendingPolicy


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


def test_firewall_blocks_replayed_idempotency_key() -> None:
    firewall = TransactionFirewall(FirewallConfig(SpendingPolicy(Decimal("100"), "EUR")))
    treasury = SandboxTreasury(firewall, balance=Decimal("500"))
    first = treasury.propose_payment(Decimal("25"), "alice", "payment", idempotency_key="pay-1")
    second = treasury.propose_payment(Decimal("25"), "alice", "payment", idempotency_key="pay-1")
    assert first.committed is True
    assert second.decision == Decision.DENY
    assert second.committed is False
    assert treasury.balance == Decimal("475")


def test_firewall_enforces_daily_spend_limit() -> None:
    policy = SpendingPolicy(Decimal("100"), "EUR", max_daily_spend=Decimal("100"))
    firewall = TransactionFirewall(FirewallConfig(policy))
    treasury = SandboxTreasury(firewall, balance=Decimal("500"))
    first = treasury.propose_payment(Decimal("60"), "alice", "payment", idempotency_key="pay-1")
    second = treasury.propose_payment(Decimal("50"), "alice", "payment", idempotency_key="pay-2")
    assert first.committed is True
    assert second.decision == Decision.REVIEW
    assert second.committed is False
    assert treasury.balance == Decimal("440")


def test_execution_creates_before_and_after_audit_events() -> None:
    firewall = TransactionFirewall(FirewallConfig(SpendingPolicy(Decimal("100"), "EUR")))
    treasury = SandboxTreasury(firewall, balance=Decimal("500"))
    result = treasury.propose_payment(Decimal("25"), "alice", "payment")
    assert result.committed is True
    event_types = [event.event_type for event in firewall.audit.all()]
    assert event_types == ["authorization.evaluated", "execution.committed"]
