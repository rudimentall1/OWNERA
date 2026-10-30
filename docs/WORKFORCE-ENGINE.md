# OWNERA Workforce Engine

**Status:** Initial deterministic coordination core implemented; execution adapters and persistence are not implemented.  
**Code:** `ownera/workforce.py`  
**Tests:** `tests/test_workforce.py`

## Purpose

The Workforce Engine coordinates specialist agents that execute customer work. It is not a single “production agent” and it is not an LLM runtime. It owns the task contract, worker eligibility, assignment, dependency gates, budget checks, and independent review lifecycle.

Commercial discovery, contract approval, worker execution, delivery, customer acceptance, and payment reconciliation are separate capabilities. This module implements only the deterministic coordination boundary.

## Initial worker roles

Roles are labels for operator visibility. Actual assignment is capability-based.

| Role | Example capabilities | Responsibility |
|---|---|---|
| Commercial Researcher | `market.research`, `lead.qualify` | Find and qualify potential customers and paid work. |
| Sales Assistant | `proposal.draft`, `customer.followup.draft` | Prepare tailored offers and follow-up drafts. |
| Project Manager | `task.plan`, `dependency.manage` | Break an approved order into bounded tasks. |
| Backend Developer | `python`, `fastapi`, `database` | Implement backend work. |
| Frontend Developer | `typescript`, `react`, `ui` | Implement client-facing interfaces. |
| Game Developer | `html5.game`, `javascript` | Implement browser game work. |
| DevOps Engineer | `docker`, `linux`, `deployment` | Build and deploy approved infrastructure changes. |
| AI Engineer | `agent.integration`, `llm.integration` | Implement bounded AI and automation features. |
| QA Reviewer | `quality.review`, `test.review` | Independently assess deliverables against acceptance criteria. |
| Security Reviewer | `security.review`, `threat.model` | Independently assess security-sensitive work. |
| Delivery Assistant | `delivery.package`, `docs.prepare` | Prepare handover artifacts and release notes. |

Do not instantiate every role as a permanent agent. A role may be implemented by a reusable worker profile and a selected model/tool runtime. Spawn workers only when an approved workload justifies their cost.

## Task lifecycle

```text
PLANNED
   |
   | dependencies accepted + capable worker available
   v
ASSIGNED
   |
   | assigned worker starts
   v
IN_PROGRESS
   |
   | submits summary + artifact references + actual cost
   v
READY_FOR_REVIEW
   |
   +---- independent reviewer accepts ----> ACCEPTED
   |
   +---- reviewer rejects ---------------> REWORK_REQUIRED
                                               |
                                               +---- reassign
```

A task cannot be assigned until all dependencies are accepted. The assigned worker cannot review its own output. A submission without artifact references is rejected. A submission above its task budget is blocked and requires a separate owner-level decision; it is not silently accepted.

## Current implementation

`WorkforceEngine` currently provides:

- worker registration with capabilities and concurrency limits;
- task creation with required capabilities, budget, acceptance criteria and dependencies;
- deterministic assignment to the least-loaded eligible worker, with worker ID as a stable tie-breaker;
- explicit start and submit transitions;
- artifact-reference requirement on submission;
- actual-cost validation against the task budget;
- independent review by a worker with `quality.review`;
- acceptance or rework decision and an in-memory review record.

The current implementation is in-memory and synchronous. It does not persist tasks, start model runtimes, execute code, call external services, manage credentials, submit customer messages, sign transactions, or verify customer payment.

## Security and authority boundaries

1. A worker profile is not an authorization grant for arbitrary tools.
2. A task's budget limit is a local task constraint, not permission to spend owner funds.
3. Customer contracts, quotes, external messages, purchases, deployments, and other consequential actions must pass through separate OWNERA policy and approval controls.
4. Workers receive scoped task inputs, not owner credentials, wallet keys, exchange withdrawal keys, or broad host access.
5. Execution adapters must use isolated environments and bounded resource limits.
6. Deliverables require evidence references and independent review. A worker saying “done” is not proof.
7. Revenue is recorded only after settlement is independently verified and reconciled against costs, fees, refunds and obligations.
8. Sovereign Reserve remains outside worker authority.

## Next implementation gates

### Gate 1 — Persistence and audit

- Persist worker, task, transition and review records.
- Emit append-only events with correlation IDs and timestamps.
- Add idempotent transition handling and recovery after process restart.

### Gate 2 — Isolated execution adapter

- Define a provider-neutral worker runtime protocol.
- Execute one bounded task in a dedicated unprivileged container or remote runner.
- Enforce CPU, memory, wall-clock, output and network limits.
- Do not mount host Docker socket or owner secrets.

### Gate 3 — First commercial delivery loop

- Add a narrow service catalog with fixed scope and acceptance criteria.
- Convert an owner-approved paid order into a task graph.
- Assign implementation and QA workers.
- Produce a reviewable artifact and handover package.
- Keep customer commitments and delivery submission owner-approved.

### Gate 4 — Verified economics

- Record actual compute/model/tool costs per task.
- Track order revenue only after confirmed settlement.
- Calculate realized net profit/loss per order.
- Expand worker roles only when repeatable positive unit economics are demonstrated.

## Definition of first success

One owner-approved paid order is converted into a task graph, executed by at least one specialist worker, independently reviewed by a different worker, delivered with inspectable artifacts, and reconciled after confirmed payment. No simulated payment or unverified completion counts.
