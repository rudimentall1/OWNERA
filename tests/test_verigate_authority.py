import base64
import hashlib
import json
import time
import unittest
from decimal import Decimal
from uuid import uuid4

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from ownera.authorization import AuthorizationError
from ownera.domain import Decision, Money, PaymentIntent
from ownera.firewall import AuthorizationDecision
from ownera.verigate import VerigateAuthorityAdapter


class FakeTransport:
    def __init__(self, authorization):
        self.authorization = authorization
        self.requests = []

    def request(self, path, payload):
        self.requests.append((path, payload))
        if path == "/v1/actions/authorize":
            return {"execution_authorization": self.authorization}
        if path == "/v1/execution/consume":
            return {"execute": True, "reason": "authorization consumed"}
        raise AssertionError(path)


def canonical(payload):
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode()


class VerigateAuthorityAdapterTest(unittest.TestCase):
    def _intent_and_adapter(self):
        intent = PaymentIntent(
            amount=Money(Decimal("0.100000000000000001"), "EUR"),
            destination="merchant-1",
            purpose="invoice",
            idempotency_key="invoice-1",
        )
        financial = intent.to_financial_action("agent-1")
        action = {
            "agent_id": "agent-1",
            "action_type": "payment",
            "target": "merchant-1",
            "amount": None,
            "amount_exact": "0.100000000000000001",
            "asset": "EUR",
            "network": None,
            "purpose": "invoice",
            "metadata": {
                "ownera_financial_action_sha256": financial.digest(),
            },
            "intent_id": str(intent.id),
        }
        payload = {
            "authorization_version": 1,
            "authorization_id": hashlib.sha256(b"authorization").hexdigest(),
            "intent_id": str(intent.id),
            "agent_id": "agent-1",
            "policy_sha256": "a" * 64,
            "capability_id": "cap-1",
            "capability_sha256": "b" * 64,
            "issued_at": int(time.time()) - 1,
            "expires_at": int(time.time()) + 300,
            "nonce": str(intent.id),
            "action": action,
        }
        issuer = Ed25519PrivateKey.generate()
        signature = base64.b64encode(issuer.sign(canonical(payload))).decode()
        envelope = {
            "payload": payload,
            "signature": signature,
            "algorithm": "Ed25519",
        }
        transport = FakeTransport(envelope)
        adapter = VerigateAuthorityAdapter.create(
            transport,
            issuer.public_key(),
            agent_id="agent-1",
            identity_id="identity-1",
            capability_id="cap-1",
            sign_action=lambda _identity_id, _action: "agent-signature",
        )
        return intent, adapter

    def test_issue_binds_exact_financial_action(self):
        intent, adapter = self._intent_and_adapter()
        verdict = AuthorizationDecision(
            intent_id=intent.id,
            decision=Decision.ALLOW,
            reasons=(),
            correlation_id=uuid4(),
        )
        authorization = adapter.issue(
            intent,
            verdict,
            policy_version="v1",
        )
        self.assertEqual(authorization.provider, "verigate")
        self.assertEqual(
            authorization.provider_authorization["payload"]["action"]["amount_exact"],
            "0.100000000000000001",
        )

    def test_tampered_provider_amount_is_rejected(self):
        intent, adapter = self._intent_and_adapter()
        verdict = AuthorizationDecision(intent.id, Decision.ALLOW, (), uuid4())
        original = adapter.transport.authorization["payload"]["action"]["amount_exact"]
        adapter.transport.authorization["payload"]["action"]["amount_exact"] = "0.1"
        with self.assertRaises(AuthorizationError):
            adapter.issue(intent, verdict, policy_version="v1")
        adapter.transport.authorization["payload"]["action"]["amount_exact"] = original

    def test_consume_is_fail_closed_on_provider_rejection(self):
        intent, adapter = self._intent_and_adapter()
        verdict = AuthorizationDecision(intent.id, Decision.ALLOW, (), uuid4())
        authorization = adapter.issue(intent, verdict, policy_version="v1")
        adapter.transport.authorization = {
            **adapter.transport.authorization,
        }
        adapter.transport.authorization = {
            "payload": authorization.provider_authorization["payload"],
            "signature": authorization.provider_authorization["signature"],
            "algorithm": "Ed25519",
        }
        adapter.transport.request = lambda path, payload: {
            "execute": False,
            "reason": "replay",
        }
        with self.assertRaises(AuthorizationError):
            adapter.consume(authorization, intent)

    def test_invalid_signature_is_rejected(self):
        intent, adapter = self._intent_and_adapter()
        verdict = AuthorizationDecision(intent.id, Decision.ALLOW, (), uuid4())
        envelope = adapter.transport.authorization
        envelope["signature"] = base64.b64encode(Ed25519PrivateKey.generate().sign(canonical(envelope["payload"]))).decode()
        with self.assertRaises(Exception):
            adapter.issue(intent, verdict, policy_version="v1")


if __name__ == "__main__":
    unittest.main()
