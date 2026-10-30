# OWNERA Order-to-Workforce Handoff

**Status:** Deterministic bridge implemented with atomic task-graph registration. The handoff registry itself remains in memory; no durable order idempotency, customer verification provider, contract-signature verification, task execution, or payment integration is implemented.  
**Code:** `ownera/order_handoff.py`  
**Tests:** `tests/test_order_handoff.py`

## Purpose

The bridge converts a confirmed customer order into a bounded workforce task graph. It closes the gap between proposal approval and actual work authorization.

These are separate events:
1. A commercial opportunity is qualified.
2. A proposal is approved by the owner for submission.
3. A customer accepts the exact quoted amount and scope.
4. The owner approves accepting the order and defines an execution budget.
5. The bridge creates tasks for the Workforce Engine.

An approved proposal alone is not an order. A customer acceptance alone does not authorize OWNERA to spend or commit its resources.

## Required order evidence

A `CustomerOrder` requires:
- proposal ID;
- customer reference;
- accepted amount and currency;
- customer acceptance evidence reference and timestamp;
- the exact accepted scope and acceptance criteria;
- owner approval identity and timestamp;
- execution budget limit.

The initial implementation validates that the order references the approved proposal, the accepted amount equals the proposal quote, currencies match, the accepted scope and acceptance criteria exactly match the approved proposal, owner approval follows proposal approval and precedes customer acceptance, and the execution budget does not exceed accepted revenue.

The acceptance reference is a provenance pointer. This version does not cryptographically verify a signature, authenticate the customer, or validate contract enforceability.

## Task plan

A task plan is an ordered tuple of `TaskSpec` entries. Each task defines:
- title and description;
- required worker capabilities;
- its own budget limit;
- acceptance criteria;
- dependencies by earlier task index.

Dependencies must refer only to earlier tasks, which prevents cycles in this initial ordered-plan format. The sum of task budgets must not exceed the order's approved execution budget.

Tasks are created as `PLANNED`. When used with `PersistentWorkforce`, the complete task graph is committed as one versioned SQLite snapshot. The workforce batch operation validates all IDs and dependencies before mutating state, so invalid batches cannot leave a partial graph. The bridge does not assign workers, start execution, contact customers, deploy code, or deliver work.

## Idempotency

The bridge records converted order IDs in memory and rejects a second conversion of the same order during the current process. The task graph is persisted atomically when the bridge receives a `PersistentWorkforce`, but the order-to-handoff association is not yet committed in the same database transaction. After a process restart, the same order could therefore be converted again. Durable order idempotency and a transaction spanning order registration plus workforce snapshot creation remain mandatory before production use.

## Next gates

1. Persist orders, proposal versions, approvals, evidence and handoff records transactionally.
2. Verify customer acceptance using an appropriate signature or trusted platform receipt where available.
3. Bind the accepted scope and acceptance criteria to an immutable proposal/order version.
4. Add task graph validation for capability coverage and realistic cost estimates.
5. Add a sandboxed worker runtime and independent QA execution.
6. Record customer delivery acceptance and independently verified settlement.

No revenue is recognized by creating an order or task graph. Revenue is recognized only after confirmed payment and reconciliation.
