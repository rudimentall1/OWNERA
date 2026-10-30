# OWNERA Workforce Persistence

**Status:** Initial SQLite snapshot persistence for the workforce engine is implemented. Commercial and order aggregates remain in memory.  
**Code:** `ownera/workforce_repository.py`, `ownera/persistent_workforce.py`, `ownera/workforce.py`  
**Tests:** `tests/test_workforce_repository.py`

## What is persisted

The repository stores a complete versioned snapshot of:
- worker profiles and capabilities;
- task definitions, dependencies and lifecycle status;
- assigned worker, execution cost and submitted artifact references;
- result summaries and reviewer references;
- review decisions, findings and timestamps.

Decimal values are serialized as strings. UUIDs and timestamps use canonical textual representations. The snapshot payload is hashed with SHA-256 and verified before restoration.

## Automatic transition persistence

Use `PersistentWorkforce` as the application-facing facade instead of calling `WorkforceEngine` directly. Worker registration, task creation, assignment, start, submission and review are saved before the command returns successfully. If a save fails, the facade reloads the last committed snapshot and raises the error. A stale process cannot silently overwrite a newer snapshot; it receives a version conflict and refreshes to committed state.

The facade is synchronous and uses one whole-workforce snapshot. It is suitable for the current single-process MVP and basic stale-writer detection, not a distributed job queue or high-throughput multi-tenant service.

## Save protocol

Each save requires the caller's expected snapshot version. The repository uses a SQLite `BEGIN IMMEDIATE` transaction and rejects stale writers. A successful save increments the snapshot version exactly once.

This is whole-state snapshot persistence, not event sourcing. The separate event store remains an append-only audit primitive and is not yet integrated with workforce transitions.

## Recovery

On startup, load the snapshot and restore a `WorkforceEngine` instance. A missing snapshot means the workforce has not yet been initialized. A digest mismatch or invalid schema must stop recovery; the application must not silently start with an empty workforce and discard the damaged state.

## Current limits

- One primary workforce snapshot per database.
- Whole-workforce snapshot writes on each transition may become expensive as task history grows.
- No atomic transaction spanning order handoff and workforce persistence yet.
- No commercial opportunity, assessment, proposal or order repositories.
- No encrypted database, automated backup, restore drill or external hash checkpoint.
- Snapshot integrity is tamper-evident, not tamper-proof against a privileged attacker able to rewrite the payload and digest.

## Next production gates

1. Replace whole-state snapshots with transactional aggregate/event persistence as workload grows.
2. Add transactional order handoff so a crash cannot create partial task graphs.
3. Add repositories for commercial opportunities, assessments, proposals and customer orders.
4. Add backup, restore and crash-injection tests.
5. Add a startup recovery check that refuses unsafe partial initialization.
6. Add an isolated worker runtime only after durable task state and recovery are reliable.
