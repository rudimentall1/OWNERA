"""Owner-attested receipt ledger for accepted OWNERA orders.

This ledger records what an owner says was received. It does not independently
verify bank transfers, payment-provider events, invoices, or on-chain transfers.
"""
from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from uuid import UUID, uuid4

from ownera.event_store import SQLiteEventStore


class SettlementError(RuntimeError):
    """Base error for receipt-ledger operations."""


class ReceiptConflict(SettlementError):
    """An idempotency key or order terms conflict with an existing record."""


class ReceiptLimitExceeded(SettlementError):
    """Recorded receipts would exceed the accepted order amount."""


class SettlementIntegrityError(SettlementError):
    """Receipt rows do not match their append-only event evidence."""


@dataclass(frozen=True)
class ReceiptRecord:
    receipt_id: UUID
    order_id: UUID
    accepted_amount: Decimal
    amount: Decimal
    currency: str
    payment_reference: str
    evidence_sha256: str
    recorded_by: str
    recorded_at: datetime
    idempotency_key: str
    verification_level: str = "OWNER_ATTESTED"


class SQLiteSettlementLedger:
    """Append-only SQLite ledger for owner-attested incoming receipts."""

    def __init__(self, database_path: str | Path) -> None:
        self.database_path = str(database_path)
        if self.database_path == ":memory:":
            raise ValueError("settlement ledger requires a file-backed database")
        Path(self.database_path).parent.mkdir(parents=True, exist_ok=True)
        self.event_store = SQLiteEventStore(database_path)
        connection = self._connect()
        try:
            connection.execute("""
                CREATE TABLE IF NOT EXISTS settlement_receipts (
                    receipt_id TEXT PRIMARY KEY,
                    order_id TEXT NOT NULL,
                    accepted_amount TEXT NOT NULL,
                    amount TEXT NOT NULL,
                    currency TEXT NOT NULL,
                    payment_reference TEXT NOT NULL,
                    evidence_sha256 TEXT NOT NULL,
                    recorded_by TEXT NOT NULL,
                    recorded_at TEXT NOT NULL,
                    idempotency_key TEXT NOT NULL UNIQUE,
                    verification_level TEXT NOT NULL
                        CHECK(verification_level = 'OWNER_ATTESTED')
                )
            """)
            connection.execute("""
                CREATE INDEX IF NOT EXISTS idx_settlement_receipts_order
                ON settlement_receipts(order_id, recorded_at)
            """)
        finally:
            connection.close()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(
            self.database_path, timeout=10, isolation_level=None
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout = 10000")
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA synchronous = FULL")
        return connection

    def _record_receipt(
        self,
        *,
        order_id: UUID,
        accepted_amount: Decimal,
        amount: Decimal,
        currency: str,
        payment_reference: str,
        evidence_sha256: str,
        recorded_by: str,
        idempotency_key: str,
        recorded_at: datetime | None = None,
    ) -> ReceiptRecord:
        accepted = self._money(accepted_amount, "accepted_amount")
        received = self._money(amount, "amount")
        normalized_currency = currency.upper()
        if accepted <= 0 or received <= 0:
            raise ValueError("accepted_amount and amount must be positive")
        if len(normalized_currency) != 3 or not normalized_currency.isalpha():
            raise ValueError("currency must be a three-letter code")
        if not payment_reference.strip() or not recorded_by.strip():
            raise ValueError("payment_reference and recorded_by are required")
        if not re.fullmatch(r"[0-9a-f]{64}", evidence_sha256):
            raise ValueError("evidence_sha256 must be a lowercase SHA-256 digest")
        if not idempotency_key.strip():
            raise ValueError("idempotency_key is required")
        timestamp = recorded_at or datetime.now(timezone.utc)
        if timestamp.tzinfo is None:
            raise ValueError("recorded_at must be timezone-aware")
        timestamp_text = timestamp.astimezone(timezone.utc).isoformat()

        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                "SELECT * FROM settlement_receipts WHERE idempotency_key = ?",
                (idempotency_key,),
            ).fetchone()
            if existing is not None:
                candidate = (
                    str(order_id), str(accepted), str(received), normalized_currency,
                    payment_reference, evidence_sha256, recorded_by,
                )
                stored = (
                    existing["order_id"], existing["accepted_amount"],
                    existing["amount"], existing["currency"],
                    existing["payment_reference"], existing["evidence_sha256"],
                    existing["recorded_by"],
                )
                if candidate != stored:
                    raise ReceiptConflict("idempotency key reused with different receipt data")
                connection.commit()
                return self._to_record(existing)

            prior = connection.execute(
                """SELECT accepted_amount, currency, amount
                   FROM settlement_receipts WHERE order_id = ?""",
                (str(order_id),),
            ).fetchall()
            if prior and any(
                row["accepted_amount"] != str(accepted)
                or row["currency"] != normalized_currency
                for row in prior
            ):
                raise ReceiptConflict("accepted order amount or currency changed")
            total = sum((Decimal(row["amount"]) for row in prior), Decimal("0"))
            if total + received > accepted:
                raise ReceiptLimitExceeded(
                    "cumulative receipts cannot exceed the accepted order amount"
                )

            receipt_id = uuid4()
            event_version = len(
                self.event_store.load("settlement_receipts", str(order_id))
            )
            self.event_store.append_in_transaction(
                connection,
                aggregate_type="settlement_receipts",
                aggregate_id=str(order_id),
                event_type="ReceiptOwnerAttested",
                payload={
                    "receipt_id": str(receipt_id),
                    "amount": str(received),
                    "accepted_amount": str(accepted),
                    "currency": normalized_currency,
                    "payment_reference": payment_reference,
                    "evidence_sha256": evidence_sha256,
                    "recorded_by": recorded_by,
                    "verification_level": "OWNER_ATTESTED",
                },
                expected_version=event_version,
                idempotency_key=f"receipt:{idempotency_key}",
                occurred_at=timestamp,
            )
            connection.execute(
                """INSERT INTO settlement_receipts (
                    receipt_id, order_id, accepted_amount, amount, currency,
                    payment_reference, evidence_sha256, recorded_by, recorded_at,
                    idempotency_key, verification_level
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'OWNER_ATTESTED')""",
                (
                    str(receipt_id), str(order_id), str(accepted), str(received),
                    normalized_currency, payment_reference, evidence_sha256,
                    recorded_by, timestamp_text, idempotency_key,
                ),
            )
            connection.commit()
            return ReceiptRecord(
                receipt_id=receipt_id, order_id=order_id,
                accepted_amount=accepted, amount=received,
                currency=normalized_currency, payment_reference=payment_reference,
                evidence_sha256=evidence_sha256, recorded_by=recorded_by,
                recorded_at=datetime.fromisoformat(timestamp_text),
                idempotency_key=idempotency_key,
            )
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def list_for_order(self, order_id: UUID) -> tuple[ReceiptRecord, ...]:
        connection = self._connect()
        try:
            rows = connection.execute(
                """SELECT * FROM settlement_receipts
                   WHERE order_id = ? ORDER BY recorded_at, receipt_id""",
                (str(order_id),),
            ).fetchall()
        finally:
            connection.close()
        return tuple(self._to_record(row) for row in rows)

    def total_owner_attested(self, order_id: UUID) -> Decimal:
        return sum(
            (record.amount for record in self.list_for_order(order_id)),
            Decimal("0"),
        )

    def verify(self, order_id: UUID) -> bool:
        aggregate_id = str(order_id)
        self.event_store.verify("settlement_receipts", aggregate_id)
        records = self.list_for_order(order_id)
        events = self.event_store.load("settlement_receipts", aggregate_id)
        if len(records) != len(events):
            raise SettlementIntegrityError("receipt rows and event history differ in length")
        by_id = {str(record.receipt_id): record for record in records}
        if len(by_id) != len(records):
            raise SettlementIntegrityError("duplicate receipt identifiers")
        for event in events:
            payload = event.payload
            record = by_id.get(payload.get("receipt_id"))
            if record is None:
                raise SettlementIntegrityError("event references a missing receipt row")
            expected = {
                "amount": str(record.amount),
                "accepted_amount": str(record.accepted_amount),
                "currency": record.currency,
                "payment_reference": record.payment_reference,
                "evidence_sha256": record.evidence_sha256,
                "recorded_by": record.recorded_by,
                "verification_level": record.verification_level,
            }
            if any(payload.get(key) != value for key, value in expected.items()):
                raise SettlementIntegrityError("receipt row differs from event evidence")
        return True

    @staticmethod
    def _money(value: Decimal, name: str) -> Decimal:
        if isinstance(value, (float, bool)):
            raise TypeError(f"{name} must not use float or boolean values")
        try:
            amount = Decimal(value)
        except (InvalidOperation, TypeError, ValueError) as exc:
            raise ValueError(f"{name} must be a valid decimal amount") from exc
        if not amount.is_finite():
            raise ValueError(f"{name} must be finite")
        return amount

    @staticmethod
    def _to_record(row: sqlite3.Row) -> ReceiptRecord:
        return ReceiptRecord(
            receipt_id=UUID(row["receipt_id"]),
            order_id=UUID(row["order_id"]),
            accepted_amount=Decimal(row["accepted_amount"]),
            amount=Decimal(row["amount"]),
            currency=row["currency"],
            payment_reference=row["payment_reference"],
            evidence_sha256=row["evidence_sha256"],
            recorded_by=row["recorded_by"],
            recorded_at=datetime.fromisoformat(row["recorded_at"]),
            idempotency_key=row["idempotency_key"],
            verification_level=row["verification_level"],
        )
