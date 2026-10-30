# OWNERA Persistent Event Store

**Status:** Durable SQLite event-store primitive implemented. Workforce and commercial domain state now also have separate versioned snapshot repositories. The event store is not yet wired into those domain transitions.  
**Code:** `ownera/event_store.py`  
**Tests:** `tests/test_event_store.py`

## Why this exists

The initial Commercial Engine, Workforce Engine and Order-to-Workforce Bridge began as in-memory domain prototypes. File-backed snapshot persistence now restores commercial opportunities, assessments, qualification results, proposals and owner approvals, as well as workforce tasks and reviews. The event store remains a separate primitive and does not yet record these transitions.

This module introduces a file-backed persistence primitive without changing those domain APIs prematurely.

## Stored event model

Each event contains:
- event UUID;
- aggregate type and aggregate ID;
- monotonically increasing aggregate version;
- event type;
- canonical JSON payload;
- UTC timestamp;
- optional idempotency key;
- previous event hash;
- current SHA-256 event hash.

The SQLite schema enforces unique aggregate versions and globally unique idempotency keys. Writes use `BEGIN IMMEDIATE` and optimistic expected-version checks. WAL mode and FULL synchronous mode are enabled for the file-backed database.

## Integrity and concurrency

Events are hash-chained per aggregate. `verify(aggregate_type, aggregate_id)` recomputes each event hash and checks the version sequence and predecessor links.

This is tamper-evident, not tamper-proof. A privileged attacker who can rewrite the entire database and recompute every hash can replace the history. Production hardening requires external checkpoints or signatures, protected backups, access controls and monitoring.

Optimistic concurrency prevents two writers from silently appending to the same aggregate version. An idempotency key safely returns the original event for an identical request and rejects reuse for different event content.

## Deliberate limitations

- File-backed SQLite only; use a temporary file in tests rather than an in-memory connection.
- No ORM or external dependency; Python standard library only.
- Commercial and workforce snapshot repositories exist, but are separate from this event store.
- No event replay into CommercialEngine, WorkforceEngine or OrderToWorkforceBridge yet.
- No snapshots, multi-process deployment guarantees beyond SQLite locking, backup automation, encryption-at-rest configuration or remote replication.
- The event store does not authorize business transitions. Domain services must validate first, then append the corresponding event.

## Next integration sequence

1. Integrate append-only commercial, order and workforce transition events with their snapshot writes.
2. Add durable customer acceptance and contract evidence before order creation.
3. Add append-only approval and audit records with actor, timestamp, policy version and evidence reference.
4. Add backup/restore tests and crash-recovery tests across all repositories.
5. Move to PostgreSQL only when concurrent deployment or operational requirements justify it.

## Production acceptance gate

A process restart must restore the exact proposal, approval, order, task and review state. Duplicate requests must not create duplicate work. A modified event must fail integrity verification. A stale writer must not overwrite a newer aggregate version. Backups must be restorable and verified.
