# Worker Quality Gate

**Status:** Initial structured, evidence-bound review gate implemented and CI-verified.  
**Code:** `ownera/quality_gate.py`  
**Tests:** `tests/test_quality_gate.py`

## Decision contract

The caller supplies only the task ID and reviewer ID. The gate itself reloads the `ArtifactReviewPacket` through `ArtifactReviewService` immediately before validation, so callers cannot forge packet contents or digest membership.

For each task acceptance criterion, the reviewer submits exactly one `CriterionAssessment` with:
- the exact criterion text;
- a boolean pass/fail judgment;
- one or more SHA-256 digests from the verified packet;
- actionable notes when the criterion fails.

The gate rejects incomplete or duplicate criteria, references outside the packet, missing evidence, failed criteria without notes, stale task state, worker/reviewer mismatch, and missing overall notes.

If all criteria pass, the gate calls the existing persistent Workforce review transition with `accepted=True`. If any criterion fails, it calls the transition with `accepted=False`, moving the task to `REWORK_REQUIRED`.

## Durable report

The structured versioned report is serialized canonically and embedded in the existing review findings. It therefore travels with the `TaskReviewAccepted` or `TaskReviewRejected` event and workforce snapshot without a second database or a split transaction. `QualityGateService.extract_report` decodes it for later inspection.

## Trust boundaries

- The reviewer supplies semantic judgments. The gate checks completeness and evidence binding; it does not prove the reviewer is correct.
- SHA-256 proves byte identity, not that an artifact satisfies a criterion.
- Reviewer identity is still a Workforce profile, not a production-authenticated principal.
- The gate does not run tests, scan malware, or infer correctness from file contents.
- A later stage must add independent reviewer identity/authentication, policy on reviewer assignment, and real Docker-produced acceptance evidence.

## Acceptance criteria

- [x] Require exactly one result for every acceptance criterion.
- [x] Require evidence digests from the verified review packet for every criterion.
- [x] Require actionable notes for failed criteria and overall reviewer notes.
- [x] Reject stale tasks and mismatched packet/task worker identity.
- [x] Persist a versioned structured report through the existing Workforce review event.
- [x] Pass only when all criteria pass; otherwise return task for rework.
- [x] Run unit tests and CI on this commit.
- [x] Add an opt-in full-path integration test using real Docker-produced artifacts.
- [ ] Run the integration test against a digest-pinned worker image.
