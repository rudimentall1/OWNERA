# OWNERA Persistent Event Store

**Status:** Commercial transitions, workforce lifecycle transitions, and order handoffs commit their versioned snapshots and append-only events in one SQLite transaction.
**Code:** `ownera/event_store.py`, `ownera/commercial_repository.py`, `ownera/persistent_commercial.py`, `ownera/workforce_repository.py`, `ownera/persistent_workforce.py`
**Tests:** `tests/test_event_store.py`, `tests/test_commercial_repository.py`, `tests/test_persistent_workforce.py`

## Stored event model

Each event contains an event UUID, aggregate type and ID, monotonically increasing aggregate version, event type, canonical JSON payload, UTC timestamp, optional idempotency key, previous event hash, and current SHA-256 event hash.

The SQLite schema enforces unique aggregate versions and globally unique idempotency keys. Writes use `BEGIN IMMEDIATE` and optimistic expected-version checks. WAL mode and FULL synchronous mode are enabled for file-backed databases.

## Atomic domain persistence

Commercial transitions use the `commercial_pipeline/primary` aggregate. Opportunity discovery, assessment, proposal drafting, and owner approval each commit the commercial snapshot and matching event atomically.

Workforce transitions use the `workforce/primary` aggregate. Worker registration, task creation, assignment, start, submission, and review commit the workforce snapshot and matching event atomically. Event-version conflicts roll back the domain snapshot write.

Order-to-workforce handoff commits the task graph, unique order idempotency record, canonical customer/owner acceptance evidence, evidence digest, snapshot, and `OrderTasksHandedOff` event in one transaction. The event binds the evidence digest. Replaying an identical handoff returns the original task IDs without appending a duplicate event; changed acceptance evidence is rejected.

Acceptance evidence is integrity-checked when read by recomputing its SHA-256 digest and matching that digest against the unique `OrderTasksHandedOff` event for the order. The recorded digest is bound into the hash-chained handoff event. This proves stored-record consistency, not authenticity of the customer, contract, signature, or payment. The supplied customer acceptance reference still requires a future trusted verification adapter.

## Integrity and concurrency

Events are hash-chained per aggregate. `verify(aggregate_type, aggregate_id)` recomputes each event hash and checks the version sequence and predecessor links. Snapshot digests are checked independently.

This is tamper-evident, not tamper-proof. A privileged attacker able to rewrite the entire database and recompute every hash can replace the history. Production hardening requires external checkpoints or signatures, protected backups, access controls, and monitoring.

## Deliberate limitations

- File-backed SQLite only; tests use temporary files.
- No event replay into domain engines yet; snapshots remain the recovery source.
- No distributed queue, multi-tenant isolation, automated backup, encryption-at-rest configuration, or remote replication.
- Whole-state snapshots are rewritten on each transition.
- The event store records validated domain transitions; it does not authorize them or execute agents.

## Next integration sequence

1. Add trusted verification of customer acceptance references and contract/signature evidence.
2. Add backup/restore and crash-recovery tests across repositories.
3. Add external event checkpoints or signatures.
4. Move to PostgreSQL only when concurrent deployment or operational requirements justify it.

## Production acceptance gate

A process restart must restore exact proposal, approval, order, task, and review state. Duplicate requests must not create duplicate work. A modified snapshot or event must fail integrity verification. A stale writer must not overwrite a newer aggregate version. Backups must be restorable and verified.
