# NEAR Agent Market to isolated worker execution

`ownera.near_market_dispatch` connects a **trusted, already-started** marketplace assignment to the existing persistent workforce, Docker worker runtime, content-addressed artifact registry, and local workforce submission.

## Contract and safety gates

- The marketplace assignment must report `started` or `in_progress`. This module does not start marketplace assignments.
- A trusted planner must provide an explicit `AssignmentExecutionSpec`: bounded command, requested artifact paths, required capabilities, acceptance criteria, budget, and summary. Marketplace title/description text is never interpreted as a shell command.
- The task ID is deterministic from the assignment ID. The worker must be registered with the exact expected profile.
- Existing assignments receive a durable execution claim in `near_market_execution_claims`. A second attempt is rejected. A claim left `RUNNING` after a crash requires reconciliation; it is not automatically retried because execution may have side effects.
- `WorkerExecutionService` validates the workforce state, budget, exit status, task identity, and requested artifacts before recording SHA-256 artifact references and moving the local task to `READY_FOR_REVIEW`.
- Actual cost is supplied by the trusted caller. Until runtime metering is connected, it must not be represented as measured spend.

## Explicitly not implemented

The module does not call the marketplace start or submit endpoints, does not approve work, and does not claim a payout. The authenticated assignment API currently returns zero assignments, and its live write contract has not been verified against an authoritative API specification. Do not infer endpoint paths or request bodies. Marketplace submission remains a separate adapter to add after contract verification.

## Verification

The dispatch path is covered by unit tests and was exercised on the server with the pinned `python:3.12-slim` image. The local smoke test created one artifact inside Docker, registered its SHA-256 digest, and submitted the local workforce task for review. This was a local test, not a marketplace order, delivery, or payment.
