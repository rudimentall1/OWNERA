# Worker Execution Submission Bridge

**Status:** Initial orchestration bridge implemented; real Docker and full CI acceptance pending.  
**Code:** `ownera/worker_execution.py`  
**Tests:** `tests/test_worker_execution.py`

## Flow

1. Caller starts an assigned task through `PersistentWorkforce`.
2. The service confirms that the task is `IN_PROGRESS` and assigned to the requested worker.
3. The configured runtime executes the request.
4. A non-success status, non-zero exit code, mismatched task ID, or empty artifact set is rejected.
5. Each returned artifact is written to `SQLiteArtifactRegistry`; the registry computes and verifies its SHA-256 content address.
6. The service submits `sha256:<digest>` references to `PersistentWorkforce.submit`.
7. Workforce persists the `TaskSubmitted` event and transitions the task to `READY_FOR_REVIEW`.

## Explicit boundaries

- The bridge does not assign/start tasks, review work, accept tasks, approve budgets, or transfer money.
- Worker identity is passed by the trusted caller; this service is not an authentication layer.
- The runtime and registry are separate components and may use separate SQLite databases. A process crash after artifact persistence but before task submission can leave unreferenced artifact records. This is safe for integrity but requires later reconciliation/retention.
- Container-relative paths are mapped to metadata names by replacing `/` with `__`; digest references remain authoritative. A future schema version should store the original relative path as a distinct field.
- This is a single-process orchestration path, not a distributed transaction or exactly-once execution guarantee.

## Acceptance criteria

- [x] Refuse execution unless task is already started and assigned to the worker.
- [x] Refuse unsuccessful runtime results and mismatched task IDs.
- [x] Register output bytes before submitting digest references.
- [x] Persist digest references through the existing TaskSubmitted event.
- [x] Run unit tests and CI.
- [ ] Run the complete path against a real digest-pinned Docker image.
- [ ] Add independent reviewer-side artifact loading and digest verification.
