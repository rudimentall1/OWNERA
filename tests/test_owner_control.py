from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from ownera.acceptance import TrustedCustomerKeyRegistry
from ownera.owner_control import (
    AuthenticatedPrincipal,
    OwnerControlError,
    OwnerKeyControl,
)


class StaticAuthenticator:
    def __init__(self, principals):
        self.principals = principals

    def authenticate(self, credential):
        if credential not in self.principals:
            raise ValueError("invalid credential")
        return self.principals[credential]


def _principal(*, roles=frozenset({"owner:key_admin"}), expires=None):
    now = datetime.now(timezone.utc)
    return AuthenticatedPrincipal(
        issuer="https://identity.example.test",
        subject="owner-42",
        roles=roles,
        authenticated_at=now - timedelta(seconds=1),
        expires_at=expires or now + timedelta(minutes=5),
        authentication_method="webauthn",
        session_id="session-abc",
    )


def _public_key():
    return Ed25519PrivateKey.generate().public_key().public_bytes(
        Encoding.Raw, PublicFormat.Raw
    )


def test_owner_can_enroll_and_actor_is_taken_from_verified_identity(tmp_path):
    registry = TrustedCustomerKeyRegistry(tmp_path / "keys.sqlite3")
    auth = StaticAuthenticator({"valid-token": _principal()})
    control = OwnerKeyControl(registry, auth)

    control.enroll("valid-token", "customer-1", "key-1", _public_key())

    event = registry.audit_events()[0]
    assert event["actor_id"] == "owner-42"
    assert event["event_type"] == "KEY_ENROLLED"
    assert registry.get_active("customer-1", "key-1").active
    registry.close()


@pytest.mark.parametrize(
    "roles",
    [
        frozenset(),
        frozenset({"customer"}),
        frozenset({"worker"}),
        frozenset({"owner:read"}),
    ],
)
def test_non_admin_roles_cannot_change_trusted_keys(tmp_path, roles):
    registry = TrustedCustomerKeyRegistry(tmp_path / "keys.sqlite3")
    auth = StaticAuthenticator({"limited-token": _principal(roles=roles)})
    control = OwnerKeyControl(registry, auth)

    with pytest.raises(OwnerControlError, match="permission required"):
        control.enroll("limited-token", "customer-1", "key-1", _public_key())

    assert registry.audit_events() == ()
    registry.close()


def test_invalid_credential_fails_closed_without_audit_event(tmp_path):
    registry = TrustedCustomerKeyRegistry(tmp_path / "keys.sqlite3")
    control = OwnerKeyControl(registry, StaticAuthenticator({}))

    with pytest.raises(OwnerControlError, match="authentication failed"):
        control.enroll("forged-token", "customer-1", "key-1", _public_key())

    assert registry.audit_events() == ()
    registry.close()


def test_expired_authenticated_principal_is_rejected(tmp_path):
    registry = TrustedCustomerKeyRegistry(tmp_path / "keys.sqlite3")
    expired = _principal(expires=datetime.now(timezone.utc) - timedelta(seconds=1))
    control = OwnerKeyControl(
        registry, StaticAuthenticator({"expired-token": expired})
    )

    with pytest.raises(OwnerControlError, match="invalid or expired"):
        control.enroll("expired-token", "customer-1", "key-1", _public_key())

    assert registry.audit_events() == ()
    registry.close()


def test_owner_rotation_and_revocation_are_audited(tmp_path):
    registry = TrustedCustomerKeyRegistry(tmp_path / "keys.sqlite3")
    control = OwnerKeyControl(
        registry, StaticAuthenticator({"valid-token": _principal()})
    )
    control.enroll("valid-token", "customer-1", "key-1", _public_key())
    control.rotate(
        "valid-token", "customer-1", "key-1", "key-2", _public_key()
    )
    control.revoke("valid-token", "customer-1", "key-2")

    events = registry.audit_events()
    assert [event["event_type"] for event in events] == [
        "KEY_ENROLLED", "KEY_REVOKED", "KEY_ENROLLED", "KEY_REVOKED"
    ]
    assert {event["actor_id"] for event in events} == {"owner-42"}
    assert registry.verify_registry_integrity()
    registry.close()


def test_invalid_authenticator_result_is_rejected(tmp_path):
    registry = TrustedCustomerKeyRegistry(tmp_path / "keys.sqlite3")
    malformed = AuthenticatedPrincipal(
        issuer="",
        subject="",
        roles=frozenset({"owner:key_admin"}),
        authenticated_at=datetime.now(timezone.utc),
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
        authentication_method="",
        session_id="",
    )
    control = OwnerKeyControl(
        registry, StaticAuthenticator({"bad": malformed})
    )

    with pytest.raises(OwnerControlError, match="invalid or expired"):
        control.enroll("bad", "customer-1", "key-1", _public_key())

    assert registry.audit_events() == ()
    registry.close()
