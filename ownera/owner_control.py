"""Authenticated owner control boundary for trusted customer key administration.

The authenticator is the security boundary: production implementations must validate
credential signatures, issuer, audience, expiry, revocation and required assurance.
This module never treats a caller-supplied actor_id or role string as identity.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol

from .acceptance import TrustedCustomerKeyRegistry


class OwnerControlError(PermissionError):
    """A credential is invalid or lacks authority for an owner operation."""


@dataclass(frozen=True)
class AuthenticatedPrincipal:
    """Identity established by a trusted authenticator, not request fields."""

    issuer: str
    subject: str
    roles: frozenset[str]
    authenticated_at: datetime
    expires_at: datetime
    authentication_method: str
    session_id: str


class CredentialAuthenticator(Protocol):
    """Adapter for a real OIDC/JWT or equivalent credential verifier."""

    def authenticate(self, credential: str) -> AuthenticatedPrincipal:
        """Validate a credential and return its verified claims."""
        ...


class OwnerKeyControl:
    """Fail-closed application service for owner-controlled customer keys."""

    REQUIRED_ROLE = "owner:key_admin"

    def __init__(
        self,
        registry: TrustedCustomerKeyRegistry,
        authenticator: CredentialAuthenticator,
    ) -> None:
        self._registry = registry
        self._authenticator = authenticator

    def _owner(self, credential: str) -> AuthenticatedPrincipal:
        if not isinstance(credential, str) or not credential.strip():
            raise OwnerControlError("owner credential is required")
        try:
            principal = self._authenticator.authenticate(credential)
        except Exception as exc:
            raise OwnerControlError("owner authentication failed") from exc

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
            raise OwnerControlError("owner key administration permission required")
        return principal

    def enroll(
        self, credential: str, customer_id: str, key_id: str, public_key: bytes
    ) -> None:
        owner = self._owner(credential)
        self._registry.enroll(
            customer_id, key_id, public_key, actor_id=owner.subject
        )

    def revoke(self, credential: str, customer_id: str, key_id: str) -> None:
        owner = self._owner(credential)
        self._registry.revoke(customer_id, key_id, actor_id=owner.subject)

    def rotate(
        self,
        credential: str,
        customer_id: str,
        old_key_id: str,
        new_key_id: str,
        new_public_key: bytes,
    ) -> None:
        owner = self._owner(credential)
        self._registry.rotate(
            customer_id,
            old_key_id,
            new_key_id,
            new_public_key,
            actor_id=owner.subject,
        )
