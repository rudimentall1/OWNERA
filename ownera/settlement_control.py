"""Authenticated owner boundary for recording settlement receipts."""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

from .owner_control import AuthenticatedPrincipal, CredentialAuthenticator, OwnerControlError
from .settlement import ReceiptRecord, SQLiteSettlementLedger


class OwnerSettlementControl:
    """Require an authenticated owner before recording receipt attestations."""

    REQUIRED_ROLE = "owner:settlement"

    def __init__(
        self,
        ledger: SQLiteSettlementLedger,
        authenticator: CredentialAuthenticator,
    ) -> None:
        self._ledger = ledger
        self._authenticator = authenticator

    def _owner(self, credential: str) -> AuthenticatedPrincipal:
        if not isinstance(credential, str) or not credential.strip():
            raise OwnerControlError("owner credential is required")
        try:
            principal = self._authenticator.authenticate(credential)
        except Exception as exc:
            raise OwnerControlError("owner authentication failed") from exc

        if not isinstance(principal, AuthenticatedPrincipal):
            raise OwnerControlError("authenticator returned an invalid principal")
        now = datetime.now(timezone.utc)
        if (
            not principal.issuer.strip()
            or not principal.subject.strip()
            or not principal.session_id.strip()
            or not principal.authentication_method.strip()
            or principal.expires_at.tzinfo is None
            or principal.expires_at <= now
            or principal.authenticated_at.tzinfo is None
            or principal.authenticated_at > now
        ):
            raise OwnerControlError("authenticated principal is invalid or expired")
        if self.REQUIRED_ROLE not in principal.roles:
            raise OwnerControlError("owner settlement permission required")
        return principal

    def record_receipt(
        self,
        credential: str,
        *,
        order_id: UUID,
        accepted_amount: Decimal,
        amount: Decimal,
        currency: str,
        payment_reference: str,
        evidence_sha256: str,
        idempotency_key: str,
        recorded_at: datetime | None = None,
    ) -> ReceiptRecord:
        owner = self._owner(credential)
        return self._ledger._record_receipt(
            order_id=order_id,
            accepted_amount=accepted_amount,
            amount=amount,
            currency=currency,
            payment_reference=payment_reference,
            evidence_sha256=evidence_sha256,
            recorded_by=owner.subject,
            idempotency_key=idempotency_key,
            recorded_at=recorded_at,
        )
