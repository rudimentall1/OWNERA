# OWNERA Workforce Persistence

**Status:** Workforce lifecycle transitions and order handoffs now commit their versioned snapshot, idempotency record where applicable, and hash-chained event in one SQLite transaction.
**Code:** `ownera/workforce_repository.py`, `ownera/persistent_workforce.py`, `ownera/workforce.py`
**Tests:** `tests/test_workforce_repository.py`, `tests/test_persistent_workforce.py`

## What is persisted

The repository stores a complete versioned snapshot of worker profiles, task definitions and dependencies, task lifecycle status, assignment, execution cost, artifact references, result summaries, reviewer references, and review decisions. Decimal values are serialized as strings. UUIDs and timestamps use canonical textual representations. The snapshot payload is hashed with SHA-256 and verified before restoration.

## Atomic lifecycle events

The application-facing `PersistentWorkforce` facade records these transitions:
- `WorkerRegistered`
- `TaskCreated`
- `TaskAssigned`
- `TaskStarted`
- `TaskSubmitted`
- `TaskReviewAccepted` or `TaskReviewRejected`

Each successful command writes the new workforce snapshot and its event in the same SQLite `BEGIN IMMEDIATE` transaction. Event payloads capture the relevant worker/task identifiers, capabilities, budget, assignment, submitted artifacts, cost, result summary, and review outcome. A failed event append rolls back the snapshot write. The facade verifies the event hash chain during initialization and refresh.

A stale process cannot silently overwrite a newer snapshot or event version. On failure, it reloads the last committed snapshot and event version before raising the original error.

## Save protocol and limits

Each save requires expected snapshot and event versions. The repository uses optimistic concurrency and increments the snapshot and event versions exactly once per accepted transition. The event aggregate is `workforce/primary`, reflecting the current single-workforce MVP.

The facade is synchronous and stores a whole-workforce snapshot on every transition. This is suitable for the current single-owner MVP, not a distributed job queue or high-throughput multi-tenant service. The event log is tamper-evident, not tamper-proof.

## Recovery

On startup, the facade verifies the workforce event chain and restores the latest integrity-checked snapshot. A digest mismatch, invalid schema, or broken event chain must stop recovery. The application must not silently initialize an empty workforce and discard damaged state.

## Remaining production gates

- Add backup, restore, crash-injection, and process-kill recovery tests.
- Add external event checkpoints or signatures, protected backups, and access controls.
- Add isolated worker execution only after durable task state and recovery are reliable.
- Replace whole-state snapshots when measured workload justifies a more granular persistence model.
