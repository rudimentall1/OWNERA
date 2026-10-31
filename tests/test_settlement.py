from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

import pytest

from ownera.owner_control import AuthenticatedPrincipal, OwnerControlError
from ownera.settlement_control import OwnerSettlementControl
from ownera.settlement import (
    ReceiptConflict,
    ReceiptLimitExceeded,
    SettlementIntegrityError,
    SQLiteSettlementLedger,
)


class StaticAuthenticator:
    def __init__(self, principals):
        self.principals = principals

    def authenticate(self, credential):
        if credential not in self.principals:
            raise ValueError("invalid credential")
        return self.principals[credential]


def _principal(*, roles=frozenset({"owner:settlement"}), expired=False):
    now = datetime.now(timezone.utc)
    return AuthenticatedPrincipal(
        issuer="https://identity.example.test",
        subject="owner-42",
        roles=roles,
        authenticated_at=now - timedelta(seconds=1),
        expires_at=now - timedelta(seconds=1) if expired else now + timedelta(minutes=5),
        authentication_method="webauthn",
        session_id="session-settlement",
    )


def _record(ledger, order_id, **overrides):
    values = {
        "order_id": order_id,
        "accepted_amount": Decimal("1000"),
        "amount": Decimal("400"),
        "currency": "EUR",
        "payment_reference": "bank-transfer:ref-123",
        "evidence_sha256": "a" * 64,
        "recorded_by": "owner-1",
        "idempotency_key": "receipt-1",
        "recorded_at": datetime(2026, 10, 31, tzinfo=timezone.utc),
    }
    values.update(overrides)
    control = OwnerSettlementControl(
        ledger, StaticAuthenticator({"valid-token": _principal()})
    )
    values.pop("recorded_by")
    return control.record_receipt("valid-token", **values)


def test_owner_attested_receipt_persists_and_verifies_event_chain(tmp_path):
    database = tmp_path / "ownera.sqlite3"
    order_id = uuid4()
    ledger = SQLiteSettlementLedger(database)

    receipt = _record(ledger, order_id)
    reopened = SQLiteSettlementLedger(database)

    assert receipt.verification_level == "OWNER_ATTESTED"
    assert reopened.total_owner_attested(order_id) == Decimal("400")
    assert reopened.list_for_order(order_id) == (receipt,)
    assert reopened.verify(order_id) is True


def test_partial_receipts_accumulate_without_exceeding_accepted_amount(tmp_path):
    ledger = SQLiteSettlementLedger(tmp_path / "ownera.sqlite3")
    order_id = uuid4()
    _record(ledger, order_id)
    _record(
        ledger, order_id, amount=Decimal("600"),
        idempotency_key="receipt-2", payment_reference="bank-transfer:ref-456",
    )

    assert ledger.total_owner_attested(order_id) == Decimal("1000")
    with pytest.raises(ReceiptLimitExceeded):
        _record(
            ledger, order_id, amount=Decimal("0.01"),
            idempotency_key="receipt-3",
        )


def test_idempotent_retry_returns_original_receipt(tmp_path):
    ledger = SQLiteSettlementLedger(tmp_path / "ownera.sqlite3")
    order_id = uuid4()

    first = _record(ledger, order_id)
    retry = _record(ledger, order_id)

    assert retry == first
    assert len(ledger.list_for_order(order_id)) == 1


def test_idempotency_key_cannot_be_reused_for_different_receipt(tmp_path):
    ledger = SQLiteSettlementLedger(tmp_path / "ownera.sqlite3")
    order_id = uuid4()
    _record(ledger, order_id)

    with pytest.raises(ReceiptConflict):
        _record(
            ledger, order_id, amount=Decimal("500"),
            payment_reference="different-reference",
        )


def test_order_terms_cannot_change_between_receipts(tmp_path):
    ledger = SQLiteSettlementLedger(tmp_path / "ownera.sqlite3")
    order_id = uuid4()
    _record(ledger, order_id)

    with pytest.raises(ReceiptConflict):
        _record(
            ledger, order_id, amount=Decimal("100"),
            idempotency_key="receipt-2",
            accepted_amount=Decimal("1200"),
        )


def test_receipt_rejects_invalid_evidence_digest_and_naive_timestamp(tmp_path):
    ledger = SQLiteSettlementLedger(tmp_path / "ownera.sqlite3")
    order_id = uuid4()

    with pytest.raises(ValueError, match="SHA-256"):
        _record(ledger, order_id, evidence_sha256="not-a-digest")
    with pytest.raises(ValueError, match="timezone-aware"):
        _record(
            ledger, order_id, idempotency_key="receipt-2",
            recorded_at=datetime(2026, 10, 31),
        )


def test_receipt_and_event_are_committed_atomically(tmp_path):
    import sqlite3

    database = tmp_path / "ownera.sqlite3"
    ledger = SQLiteSettlementLedger(database)
    order_id = uuid4()
    _record(ledger, order_id)

    assert len(ledger.event_store.load("settlement_receipts", str(order_id))) == 1
    assert ledger.verify(order_id) is True

    connection = sqlite3.connect(database)
    try:
        connection.execute(
            "UPDATE settlement_receipts SET amount = '999' WHERE order_id = ?",
            (str(order_id),),
        )
        connection.commit()
    finally:
        connection.close()

    # The hash chain alone remains valid, but row/event reconciliation detects
    # the changed financial amount.
    with pytest.raises(SettlementIntegrityError, match="differs from event"):
        ledger.verify(order_id)



def test_receipt_actor_is_derived_from_authenticated_owner(tmp_path):
    ledger = SQLiteSettlementLedger(tmp_path / "ownera.sqlite3")
    receipt = _record(ledger, uuid4())

    assert receipt.recorded_by == "owner-42"


@pytest.mark.parametrize(
    "roles",
    [frozenset(), frozenset({"customer"}), frozenset({"worker"}), frozenset({"owner:read"})],
)
def test_non_owner_cannot_record_receipts(tmp_path, roles):
    ledger = SQLiteSettlementLedger(tmp_path / "ownera.sqlite3")
    control = OwnerSettlementControl(
        ledger, StaticAuthenticator({"limited": _principal(roles=roles)})
    )

    order_id = uuid4()
    with pytest.raises(OwnerControlError, match="permission required"):
        control.record_receipt(
            "limited",
            order_id=order_id,
            accepted_amount=Decimal("100"),
            amount=Decimal("50"),
            currency="EUR",
            payment_reference="ref",
            evidence_sha256="a" * 64,
            idempotency_key="limited-1",
        )

    assert ledger.list_for_order(order_id) == ()


def test_invalid_and_expired_credentials_cannot_record_receipts(tmp_path):
    ledger = SQLiteSettlementLedger(tmp_path / "ownera.sqlite3")
    invalid = OwnerSettlementControl(ledger, StaticAuthenticator({}))
    expired = OwnerSettlementControl(
        ledger, StaticAuthenticator({"expired": _principal(expired=True)})
    )
    args = {
        "order_id": uuid4(),
        "accepted_amount": Decimal("100"),
        "amount": Decimal("50"),
        "currency": "EUR",
        "payment_reference": "ref",
        "evidence_sha256": "a" * 64,
        "idempotency_key": "invalid-1",
    }

    with pytest.raises(OwnerControlError, match="authentication failed"):
        invalid.record_receipt("forged", **args)
    with pytest.raises(OwnerControlError, match="invalid or expired"):
        expired.record_receipt("expired", **args)

    assert ledger.list_for_order(args["order_id"]) == ()



def test_malformed_authenticator_result_fails_closed(tmp_path):
    ledger = SQLiteSettlementLedger(tmp_path / "ownera.sqlite3")
    control = OwnerSettlementControl(ledger, StaticAuthenticator({"malformed": None}))

    with pytest.raises(OwnerControlError, match="invalid principal"):
        control.record_receipt(
            "malformed",
            order_id=uuid4(),
            accepted_amount=Decimal("100"),
            amount=Decimal("50"),
            currency="EUR",
            payment_reference="ref",
            evidence_sha256="a" * 64,
            idempotency_key="malformed-1",
        )
