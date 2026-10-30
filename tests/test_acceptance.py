from __future__ import annotations

import base64
from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from ownera.acceptance import (
    AcceptanceVerificationError, CustomerAcceptanceAttestation,
    TrustedCustomerKeyRegistry, acceptance_signing_payload,
    verify_customer_acceptance,
)
from ownera.commercial import ProposalDraft, ProposalStatus
from ownera.order_handoff import CustomerOrder, OrderHandoffError, OrderToWorkforceBridge, TaskSpec
from ownera.workforce import WorkforceEngine, WorkerProfile


def _signed_order():
    now = datetime.now(timezone.utc)
    proposal = ProposalDraft(
        opportunity_id=uuid4(), scope="Build API",
        acceptance_criteria=("API works", "Tests pass"),
        delivery_plan=("Build", "Review"), quote_amount=Decimal("1000"),
        currency="EUR", status=ProposalStatus.APPROVED_FOR_SUBMISSION,
        owner_approved_by="owner", owner_approved_at=now,
    )
    order = CustomerOrder(
        proposal_id=proposal.proposal_id, customer_id="customer-1",
        accepted_amount=Decimal("1000"), currency="EUR",
        customer_acceptance_ref="contract:ref", accepted_scope=proposal.scope,
        accepted_acceptance_criteria=proposal.acceptance_criteria,
        customer_accepted_at=now, owner_approved_by="owner",
        owner_approved_at=now, execution_budget_limit=Decimal("500"),
        acceptance_attestation=CustomerAcceptanceAttestation("key-1", "", "nonce-1"),
    )
    private = Ed25519PrivateKey.generate()
    public = private.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    registry = TrustedCustomerKeyRegistry()
    registry.enroll("customer-1", "key-1", public)
    signature = base64.b64encode(private.sign(acceptance_signing_payload(order))).decode()
    order = replace(order, acceptance_attestation=CustomerAcceptanceAttestation(
        "key-1", signature, "nonce-1"
    ))
    workforce = WorkforceEngine((WorkerProfile("worker", "worker", frozenset({"python"})),))
    specs = (TaskSpec("Build", "Build API", frozenset({"python"}),
                      Decimal("100"), ("API works",)),)
    return proposal, order, registry, workforce, specs


def test_valid_signature_and_strict_handoff():
    proposal, order, registry, workforce, specs = _signed_order()
    assert verify_customer_acceptance(order, registry).status == "VERIFIED"
    handoff = OrderToWorkforceBridge(
        trusted_keys=registry, require_verified_acceptance=True
    ).convert(order, proposal, specs, workforce)
    assert handoff.task_ids


def test_strict_mode_rejects_missing_attestation():
    proposal, order, registry, workforce, specs = _signed_order()
    with pytest.raises(OrderHandoffError, match="verified customer acceptance"):
        OrderToWorkforceBridge(
            trusted_keys=registry, require_verified_acceptance=True
        ).convert(replace(order, acceptance_attestation=None), proposal, specs, workforce)


def test_tampered_amount_or_scope_invalidates_signature():
    _, order, registry, _, _ = _signed_order()
    with pytest.raises(AcceptanceVerificationError, match="signature is invalid"):
        verify_customer_acceptance(replace(order, accepted_amount=Decimal("999")), registry)
    with pytest.raises(AcceptanceVerificationError, match="signature is invalid"):
        verify_customer_acceptance(replace(order, accepted_scope="changed"), registry)


def test_wrong_customer_and_revoked_key_are_rejected():
    _, order, registry, _, _ = _signed_order()
    with pytest.raises(AcceptanceVerificationError, match="missing or revoked"):
        verify_customer_acceptance(replace(order, customer_id="other"), registry)
    registry.revoke("customer-1", "key-1")
    with pytest.raises(AcceptanceVerificationError, match="missing or revoked"):
        verify_customer_acceptance(order, registry)


def test_default_legacy_path_is_persisted_as_unverified(tmp_path):
    from ownera.persistent_workforce import PersistentWorkforce

    proposal, order, _, _, specs = _signed_order()
    unsigned = replace(order, acceptance_attestation=None)
    workforce = PersistentWorkforce(tmp_path / "ownera.sqlite3")
    OrderToWorkforceBridge().convert(unsigned, proposal, specs, workforce)
    evidence = workforce.repository.load_order_acceptance_evidence(order.order_id)
    assert evidence["acceptance_verification"]["status"] == "UNVERIFIED"


def test_invalid_signature_is_rejected_before_handoff():
    proposal, order, registry, workforce, specs = _signed_order()
    broken = replace(order, acceptance_attestation=CustomerAcceptanceAttestation(
        "key-1", base64.b64encode(b"invalid-signature").decode(), "nonce-1"
    ))
    with pytest.raises(OrderHandoffError, match="signature is invalid"):
        OrderToWorkforceBridge(
            trusted_keys=registry, require_verified_acceptance=True
        ).convert(broken, proposal, specs, workforce)



def test_registry_survives_restart_and_audit_chain_verifies(tmp_path):
    from ownera.acceptance import TrustedCustomerKeyRegistry

    _, order, registry, _, _ = _signed_order()
    key = registry.get_active("customer-1", "key-1")
    database = tmp_path / "trusted-keys.sqlite3"
    registry.close()
    durable = TrustedCustomerKeyRegistry(database)
    durable.enroll(
        "customer-1", "key-1",
        base64.b64decode(key.public_key_b64), actor_id="security-admin",
    )
    assert durable.verify_audit_chain() is True
    durable.close()

    restored = TrustedCustomerKeyRegistry(database)
    assert verify_customer_acceptance(order, restored).status == "VERIFIED"
    events = restored.audit_events()
    assert len(events) == 1
    assert events[0]["actor_id"] == "security-admin"
    assert events[0]["event_type"] == "KEY_ENROLLED"
    assert restored.verify_audit_chain() is True
    restored.close()


def test_key_rotation_is_atomic_and_revokes_previous_key(tmp_path):
    from ownera.acceptance import TrustedCustomerKeyRegistry

    _, order, registry, _, _ = _signed_order()
    old = registry.get_active("customer-1", "key-1")
    database = tmp_path / "rotation.sqlite3"
    registry.close()
    durable = TrustedCustomerKeyRegistry(database)
    durable.enroll("customer-1", "key-1", base64.b64decode(old.public_key_b64))
    replacement_private = Ed25519PrivateKey.generate()
    replacement_public = replacement_private.public_key().public_bytes(
        Encoding.Raw, PublicFormat.Raw
    )
    durable.rotate(
        "customer-1", "key-1", "key-2", replacement_public,
        actor_id="security-admin",
    )
    with pytest.raises(AcceptanceVerificationError, match="missing or revoked"):
        verify_customer_acceptance(order, durable)
    replacement_order = replace(
        order,
        acceptance_attestation=CustomerAcceptanceAttestation("key-2", "", "nonce-2"),
    )
    signature = base64.b64encode(
        replacement_private.sign(acceptance_signing_payload(replacement_order))
    ).decode()
    replacement_order = replace(
        replacement_order,
        acceptance_attestation=CustomerAcceptanceAttestation("key-2", signature, "nonce-2"),
    )
    assert verify_customer_acceptance(replacement_order, durable).status == "VERIFIED"
    assert [event["event_type"] for event in durable.audit_events()] == [
        "KEY_ENROLLED", "KEY_REVOKED", "KEY_ENROLLED"
    ]
    assert durable.verify_audit_chain() is True
    durable.close()


def test_key_rotation_rolls_back_if_replacement_id_already_exists(tmp_path):
    from ownera.acceptance import TrustedCustomerKeyRegistry

    database = tmp_path / "rotation-rollback.sqlite3"
    registry = TrustedCustomerKeyRegistry(database)
    first = Ed25519PrivateKey.generate().public_key().public_bytes(
        Encoding.Raw, PublicFormat.Raw
    )
    second = Ed25519PrivateKey.generate().public_key().public_bytes(
        Encoding.Raw, PublicFormat.Raw
    )
    registry.enroll("customer", "old", first)
    registry.enroll("customer", "new", second)
    before = registry.audit_events()
    import sqlite3
    with pytest.raises(sqlite3.IntegrityError):
        registry.rotate("customer", "old", "new", second)
    assert registry.get_active("customer", "old").active is True
    assert registry.get_active("customer", "new").active is True
    assert registry.audit_events() == before
    assert registry.verify_audit_chain() is True
    registry.close()


def test_audit_chain_detects_modified_event(tmp_path):
    import sqlite3
    from ownera.acceptance import TrustedCustomerKeyRegistry, TrustedKeyRegistryError

    database = tmp_path / "audit-tamper.sqlite3"
    registry = TrustedCustomerKeyRegistry(database)
    public = Ed25519PrivateKey.generate().public_key().public_bytes(
        Encoding.Raw, PublicFormat.Raw
    )
    registry.enroll("customer", "key", public)
    registry.close()
    connection = sqlite3.connect(database)
    connection.execute(
        "UPDATE trusted_key_audit SET actor_id = ? WHERE sequence = 1",
        ("tampered-admin",),
    )
    connection.commit()
    connection.close()
    restored = TrustedCustomerKeyRegistry(database)
    with pytest.raises(TrustedKeyRegistryError, match="digest mismatch"):
        restored.verify_audit_chain()
    restored.close()


def test_registry_detects_key_table_tampering(tmp_path):
    import sqlite3
    from ownera.acceptance import TrustedCustomerKeyRegistry, TrustedKeyRegistryError

    database = tmp_path / "key-row-tamper.sqlite3"
    registry = TrustedCustomerKeyRegistry(database)
    public = Ed25519PrivateKey.generate().public_key().public_bytes(
        Encoding.Raw, PublicFormat.Raw
    )
    registry.enroll("customer", "key", public)
    registry.close()
    connection = sqlite3.connect(database)
    connection.execute(
        "UPDATE trusted_customer_keys SET active = 0 WHERE customer_id = ? AND key_id = ?",
        ("customer", "key"),
    )
    connection.commit()
    connection.close()
    restored = TrustedCustomerKeyRegistry(database)
    with pytest.raises(TrustedKeyRegistryError, match="differs from audit history"):
        restored.get_active("customer", "key")
    restored.close()


def test_verified_attestation_signature_is_persisted_with_order_evidence(tmp_path):
    from ownera.persistent_workforce import PersistentWorkforce

    proposal, order, registry, _, specs = _signed_order()
    workforce = PersistentWorkforce(tmp_path / "verified-order.sqlite3")
    OrderToWorkforceBridge(
        trusted_keys=registry, require_verified_acceptance=True
    ).convert(order, proposal, specs, workforce)
    evidence = workforce.repository.load_order_acceptance_evidence(order.order_id)
    assert evidence["acceptance_verification"]["status"] == "VERIFIED"
    assert evidence["acceptance_verification"]["key_id"] == "key-1"
    assert evidence["customer_acceptance_attestation"]["signature_b64"] == (
        order.acceptance_attestation.signature_b64
    )
    assert evidence["customer_acceptance_attestation"]["nonce"] == "nonce-1"


def test_signature_binds_criteria_reference_order_and_nonce():
    _, order, registry, _, _ = _signed_order()
    mutations = (
        {"accepted_acceptance_criteria": ("different",)},
        {"customer_acceptance_ref": "contract:other"},
        {"order_id": uuid4()},
    )
    for mutation in mutations:
        with pytest.raises(AcceptanceVerificationError, match="signature is invalid"):
            verify_customer_acceptance(replace(order, **mutation), registry)
    changed_nonce = replace(
        order,
        acceptance_attestation=replace(order.acceptance_attestation, nonce="nonce-changed"),
    )
    with pytest.raises(AcceptanceVerificationError, match="signature is invalid"):
        verify_customer_acceptance(changed_nonce, registry)
