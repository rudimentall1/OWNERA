"""Ed25519 customer acceptance verification against owner-enrolled keys."""
from __future__ import annotations
import base64
import hashlib
import json
from dataclasses import dataclass
from datetime import timezone
from decimal import Decimal
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

class AcceptanceVerificationError(ValueError):
    """An acceptance attestation cannot be trusted."""

@dataclass(frozen=True)
class CustomerAcceptanceAttestation:
    key_id: str
    signature_b64: str
    nonce: str

@dataclass(frozen=True)
class TrustedCustomerKey:
    customer_id: str
    key_id: str
    public_key_b64: str
    active: bool = True

@dataclass(frozen=True)
class AcceptanceVerification:
    status: str
    key_id: str | None
    attestation_digest: str | None
    reason: str

class TrustedCustomerKeyRegistry:
    """In-memory MVP registry. Enrollment is an owner-controlled trust decision."""
    def __init__(self) -> None:
        self._keys: dict[tuple[str, str], TrustedCustomerKey] = {}

    def enroll(self, customer_id: str, key_id: str, public_key: bytes) -> None:
        if not customer_id.strip() or not key_id.strip():
            raise ValueError("customer_id and key_id are required")
        if len(public_key) != 32:
            raise ValueError("Ed25519 public keys must be 32 bytes")
        identity = (customer_id, key_id)
        if identity in self._keys:
            raise ValueError("key_id is already enrolled for this customer")
        self._keys[identity] = TrustedCustomerKey(
            customer_id, key_id, base64.b64encode(public_key).decode("ascii")
        )

    def revoke(self, customer_id: str, key_id: str) -> None:
        key = self._keys.get((customer_id, key_id))
        if key is None:
            raise KeyError("trusted customer key not found")
        self._keys[(customer_id, key_id)] = TrustedCustomerKey(
            key.customer_id, key.key_id, key.public_key_b64, False
        )

    def get_active(self, customer_id: str, key_id: str) -> TrustedCustomerKey:
        key = self._keys.get((customer_id, key_id))
        if key is None or not key.active:
            raise AcceptanceVerificationError("trusted customer key is missing or revoked")
        return key

def acceptance_signing_payload(order: object) -> bytes:
    attestation = order.acceptance_attestation
    payload = {
        "schema_version": 1, "customer_id": order.customer_id,
        "order_id": str(order.order_id), "proposal_id": str(order.proposal_id),
        "accepted_amount": str(Decimal(order.accepted_amount)),
        "currency": order.currency.upper(), "accepted_scope": order.accepted_scope,
        "accepted_acceptance_criteria": list(order.accepted_acceptance_criteria),
        "customer_accepted_at": order.customer_accepted_at.astimezone(timezone.utc).isoformat(),
        "nonce": attestation.nonce,
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")

def verify_customer_acceptance(order: object, registry: TrustedCustomerKeyRegistry) -> AcceptanceVerification:
    attestation = order.acceptance_attestation
    if attestation is None:
        raise AcceptanceVerificationError("customer acceptance attestation is missing")
    if not attestation.nonce.strip():
        raise AcceptanceVerificationError("attestation nonce is required")
    trusted = registry.get_active(order.customer_id, attestation.key_id)
    try:
        key = Ed25519PublicKey.from_public_bytes(
            base64.b64decode(trusted.public_key_b64, validate=True)
        )
        signature = base64.b64decode(attestation.signature_b64, validate=True)
        key.verify(signature, acceptance_signing_payload(order))
    except (InvalidSignature, ValueError) as exc:
        raise AcceptanceVerificationError("customer acceptance signature is invalid") from exc
    canonical = json.dumps(
        {"key_id": attestation.key_id, "nonce": attestation.nonce,
         "signature_b64": attestation.signature_b64},
        sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    )
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return AcceptanceVerification("VERIFIED", attestation.key_id, digest, "signature_valid")
