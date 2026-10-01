import base64
import hashlib
import json
import time
from decimal import Decimal

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from ownera.domain import Decision
from ownera.firewall import FirewallConfig, TransactionFirewall
from ownera.sandbox import SandboxTreasury
from ownera.security import SpendingPolicy
from ownera.verigate import VerigateAuthorityAdapter


def canonical(payload):
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


class FakeVerigate:
    def __init__(self):
        self.issuer = Ed25519PrivateKey.generate()

    def authorize(self, request):
        action = {
            "agent_id": request["agent_id"],
            "action_type": request["action_type"],
            "target": request["target"],
            "amount_exact": request["amount_exact"],
            "asset": request["asset"],
            "purpose": request["purpose"],
            "metadata": request["metadata"],
            "intent_id": request["intent_id"],
        }
        payload = {
            "authorization_version": 1,
            "authorization_id": hashlib.sha256(
                request["intent_id"].encode()
            ).hexdigest(),
            "intent_id": request["intent_id"],
            "agent_id": request["agent_id"],
            "policy_sha256": "a" * 64,
            "capability_id": request["capability_id"],
            "capability_sha256": "b" * 64,
            "issued_at": int(time.time()) - 1,
            "expires_at": int(time.time()) + 300,
            "nonce": request["intent_id"],
            "action": action,
        }
        return {
            "execution_authorization": {
                "payload": payload,
                "signature": base64.b64encode(
                    self.issuer.sign(canonical(payload))
                ).decode(),
                "algorithm": "Ed25519",
            }
        }


class Transport:
    def __init__(self, provider):
        self.provider = provider
        self.consumed = False

    def request(self, path, payload):
        if path == "/v1/actions/authorize":
            return self.provider.authorize(payload)
        if path == "/v1/execution/consume":
            self.consumed = True
            return {"execute": True}
        raise AssertionError(path)


def test_sandbox_executes_only_after_verigate_signed_authorization():
    policy = SpendingPolicy(max_single_payment=Decimal("500"), currency="EUR")
    firewall = TransactionFirewall(FirewallConfig(policy=policy))
    provider = FakeVerigate()
    transport = Transport(provider)
    adapter = VerigateAuthorityAdapter.create(
        transport,
        provider.issuer.public_key(),
        agent_id="owner-agent",
        identity_id="identity-1",
        capability_id="capability-1",
        sign_action=lambda _identity, _action: "agent-signature",
    )
    treasury = SandboxTreasury(
        firewall,
        balance=Decimal("1000"),
        authority=adapter,
    )

    result = treasury.propose_payment(
        Decimal("100.000000000000000001"),
        "alice",
        "invoice",
        idempotency_key="integration-1",
    )

    assert result.decision == Decision.ALLOW
    assert result.committed is True
    assert result.authorization is not None
    assert result.authorization.provider == "verigate"
    assert result.receipt is not None
    assert transport.consumed is True
    assert treasury.balance == Decimal("899.999999999999999999")
