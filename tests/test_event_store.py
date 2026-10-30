from datetime import datetime

import pytest

from ownera.event_store import (
    ConcurrencyError,
    IdempotencyConflict,
    IntegrityError,
    SQLiteEventStore,
)


def test_events_survive_store_reopen_and_verify_hash_chain(tmp_path):
    database = tmp_path / "ownera.sqlite3"
    store = SQLiteEventStore(database)
    first = store.append(
        aggregate_type="opportunity",
        aggregate_id="opp-1",
        event_type="OpportunityDiscovered",
        payload={"budget": "500", "currency": "EUR"},
        expected_version=0,
    )
    store.append(
        aggregate_type="opportunity",
        aggregate_id="opp-1",
        event_type="OpportunityQualified",
        payload={"margin": "0.42"},
        expected_version=1,
    )

    reopened = SQLiteEventStore(database)
    events = reopened.load("opportunity", "opp-1")

    assert len(events) == 2
    assert events[0].event_id == first.event_id
    assert events[1].previous_hash == events[0].event_hash
    assert reopened.verify("opportunity", "opp-1") is True


def test_optimistic_concurrency_rejects_stale_writer(tmp_path):
    store = SQLiteEventStore(tmp_path / "ownera.sqlite3")
    store.append(
        aggregate_type="order",
        aggregate_id="order-1",
        event_type="OrderCreated",
        payload={},
        expected_version=0,
    )

    with pytest.raises(ConcurrencyError, match="expected version 0, found 1"):
        store.append(
            aggregate_type="order",
            aggregate_id="order-1",
            event_type="OrderAccepted",
            payload={},
            expected_version=0,
        )


def test_idempotency_key_returns_original_event_for_same_request(tmp_path):
    store = SQLiteEventStore(tmp_path / "ownera.sqlite3")
    first = store.append(
        aggregate_type="proposal",
        aggregate_id="proposal-1",
        event_type="ProposalApproved",
        payload={"owner": "owner-1"},
        expected_version=0,
        idempotency_key="approve-proposal-1",
    )
    replay = store.append(
        aggregate_type="proposal",
        aggregate_id="proposal-1",
        event_type="ProposalApproved",
        payload={"owner": "owner-1"},
        expected_version=0,
        idempotency_key="approve-proposal-1",
    )

    assert replay.event_id == first.event_id
    assert len(store.load("proposal", "proposal-1")) == 1


def test_idempotency_key_cannot_be_reused_for_different_content(tmp_path):
    store = SQLiteEventStore(tmp_path / "ownera.sqlite3")
    store.append(
        aggregate_type="proposal",
        aggregate_id="proposal-1",
        event_type="ProposalApproved",
        payload={"owner": "owner-1"},
        expected_version=0,
        idempotency_key="same-key",
    )

    with pytest.raises(IdempotencyConflict):
        store.append(
            aggregate_type="proposal",
            aggregate_id="proposal-2",
            event_type="ProposalApproved",
            payload={"owner": "owner-2"},
            expected_version=0,
            idempotency_key="same-key",
        )


def test_payload_must_be_json_safe_and_timestamp_timezone_aware(tmp_path):
    store = SQLiteEventStore(tmp_path / "ownera.sqlite3")
    with pytest.raises(ValueError, match="timezone-aware"):
        store.append(
            aggregate_type="task",
            aggregate_id="task-1",
            event_type="TaskCreated",
            payload={},
            expected_version=0,
            occurred_at=datetime(2026, 1, 1),
        )

    with pytest.raises(TypeError):
        store.append(
            aggregate_type="task",
            aggregate_id="task-1",
            event_type="TaskCreated",
            payload={"not_json": object()},
            expected_version=0,
        )


def test_hash_chain_detects_database_tampering(tmp_path):
    database = tmp_path / "ownera.sqlite3"
    store = SQLiteEventStore(database)
    store.append(
        aggregate_type="task",
        aggregate_id="task-1",
        event_type="TaskCreated",
        payload={"title": "Build API"},
        expected_version=0,
    )

    import sqlite3

    connection = sqlite3.connect(database)
    connection.execute(
        "UPDATE ownera_events SET payload_json = ? WHERE aggregate_id = ?",
        ('{"title":"tampered"}', "task-1"),
    )
    connection.commit()
    connection.close()

    with pytest.raises(IntegrityError, match="hash mismatch"):
        store.verify("task", "task-1")
