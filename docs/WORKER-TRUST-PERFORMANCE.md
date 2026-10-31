# Worker Trust & Performance

**Status:** Initial event-derived metrics implementation. Ruff and pytest CI passed on commit `bceee858` (216 passed, 8 skipped).
**Code:** `ownera/worker_performance.py`
**Tests:** `tests/test_worker_performance.py`

## Principle

Worker performance is derived from the append-only workforce event history, not from self-reported agent scores. The service verifies the workforce event hash chain before calculating metrics.

## Metrics

Per registered worker:
- task start attempts;
- submitted execution attempts;
- reviewed attempts;
- accepted attempts;
- rework attempts;
- attempts currently awaiting review;
- acceptance rate over reviewed attempts only;
- actual submitted cost grouped by currency.

A resubmission after rework is a new attempt. It is attributed to the worker ID recorded in that `TaskSubmitted` event, so reassignment does not transfer the previous worker's result to the new worker.

Pending submissions are not treated as accepted or rejected. Costs are never combined across currencies.

## Descriptive trust bands

- `UNRATED`: fewer than five reviewed attempts.
- `REVIEW_REQUIRED`: at least five reviewed attempts and acceptance rate below 70%.
- `LIMITED_EVIDENCE`: at least five reviewed attempts, but the stronger consistency threshold is not met.
- `CONSISTENT`: at least twenty reviewed attempts and acceptance rate at least 90%.

These are descriptive labels only. They do not authorize tool access, money movement, task assignment, or privilege escalation. Small samples remain unrated to avoid false confidence.

## Boundaries and known limitations

- The event chain is tamper-evident, not tamper-proof; an attacker with database rewrite access may rewrite the entire chain unless an external checkpoint exists.
- The report rejects snapshot/event-version divergence. Lifecycle idempotency keys include the snapshot version so a legitimate later retry/rework transition with the same payload is not collapsed into an earlier event.
- Cost figures are worker-submitted actual_cost values, not independently verified invoices or payments.
- Acceptance reflects the recorded reviewer decision, not an objective guarantee of quality.
- Historical attribution is based on the worker ID in each submission event.
- The initial report covers the complete retained event history; retention, privacy, and external audit export are future work.
- Metrics are not yet used by the assignment algorithm.

## Acceptance criteria

- [x] Verify event-chain integrity before reporting.
- [x] Attribute each reviewed attempt to the worker who submitted it.
- [x] Separate accepted, rework, and pending attempts.
- [x] Keep costs separated by currency.
- [x] Avoid trust labels for small samples.
- [x] Run unit tests and CI for this implementation.
- [ ] Add external event-chain checkpoints and independently verified cost/settlement evidence.
