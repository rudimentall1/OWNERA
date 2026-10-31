# Independent Artifact Review

**Status:** Initial reviewer-side loading and integrity verification implemented; human/agent quality judgment remains a separate explicit Workforce action.  
**Code:** `ownera/artifact_review.py`  
**Tests:** `tests/test_artifact_review.py`

## Contract

The reviewer service loads a task only when it is `READY_FOR_REVIEW`. It requires an enabled reviewer with `quality.review`, rejects self-review, and accepts only registered `sha256:<digest>` references. Each digest must have task-scoped registry provenance bound to the task's assigned worker. The registry recomputes SHA-256 before returning the original bytes.

The service returns an `ArtifactReviewPacket` with original bytes and metadata. It does not accept, reject, or modify the task. The reviewer must inspect the actual deliverables and then use the existing `PersistentWorkforce.review` method with findings and an explicit decision.

## Boundaries

- Digest verification establishes byte integrity, not correctness or safety.
- The workforce reviewer identity is a registered worker profile, not a cryptographically authenticated human identity.
- The current registry is single-node SQLite storage.
- Non-SHA artifact references are rejected by this review path until a separate verified evidence adapter exists.

## Acceptance criteria

- [x] Require READY_FOR_REVIEW state and a distinct enabled quality reviewer.
- [x] Require each task reference to resolve to task-scoped artifact provenance.
- [x] Bind artifact provenance to the task's assigned worker.
- [x] Return original bytes only after registry digest verification.
- [x] Keep evidence loading separate from the accept/reject decision.
- [ ] Run tests and CI on this change.
- [ ] Run independent review against real Docker-produced artifacts.
