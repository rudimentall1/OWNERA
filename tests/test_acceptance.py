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


def test_default_legacy_path_is_not_mistaken_for_verified():
    proposal, order, _, workforce, specs = _signed_order()
    unsigned = replace(order, acceptance_attestation=None)
    OrderToWorkforceBridge().convert(unsigned, proposal, specs, workforce)
