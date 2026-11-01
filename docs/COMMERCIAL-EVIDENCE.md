# Commercial Opportunity Evidence Registry

**Status:** SQLite evidence capture, owner review, integrity verification, fail-closed qualification gating, stable Immunefi source identity, semantic change tracking, and a read-only CLI intake are implemented. A daily systemd timer definition is provided in `deploy/systemd/`. The gate is enforced when `PersistentCommercialEngine` is constructed with the registry; legacy callers that omit the gate retain the previous behavior.
**Code:** `ownera/evidence_registry.py`  
**Tests:** `tests/test_evidence_registry.py`

## Purpose

The registry turns an opportunity's source material into a durable reviewable record:

1. Capture a public HTTPS source URL and bounded content snapshot.
2. Generate the evidence ID and capture timestamp inside the registry, not from caller input.
3. Calculate and store a SHA-256 digest of the exact snapshot.
4. Create an immutable-in-normal-use evidence record in `PENDING`.
5. Require an authenticated principal with `owner:commercial` to accept or reject it.
6. Record reviewer identity from the verified principal, never from request input.
7. Verify the content digest and per-evidence hash-chained audit events.

## Trust boundaries

- HTTPS confirms transport encryption to the endpoint, not that the listing is genuine.
- A content hash detects changes to the stored snapshot; it does not prove that the source told the truth.
- A source URL, captured text, bounty listing, budget, or customer claim is untrusted until reviewed.
- Owner acceptance means the owner reviewed the captured evidence. It is not proof of customer identity, legal eligibility, an enforceable contract, or payment.
- The registry uses a single-node SQLite database. Its hash chain is tamper-evident, not tamper-proof against an attacker who can rewrite the database and recompute all hashes.
- Snapshots are limited to 16,384 characters. Adapters must avoid secrets and unnecessary personal data.

## API

- `capture(...)` stores a PENDING evidence snapshot and a capture event atomically.
- `capture_source_observation(...)` binds a stable source key to one opportunity ID and semantic fingerprint. Unchanged observations reuse the existing evidence; changed terms create a new PENDING evidence version in the same SQLite transaction as the source pointer update.
- `update_source_lifecycle(...)` updates the latest observed lifecycle state only for a previously discovered source. It does not create an opportunity for a listing that has never been active.
- `source_observation(...)` exposes the latest source identity, fingerprint, evidence pointer, lifecycle state, and observation time for diagnostics.
- `review(credential, evidence_id, accept=...)` authenticates the owner, derives the reviewer from the principal, and stores the decision and event atomically.
- `require_accepted(opportunity_id, evidence_refs)` fails closed unless every reference is a registry UUID, belongs to the same opportunity, is ACCEPTED, and still matches its content digest.
- `verify(evidence_id)` checks the content digest and event hash chain.

The persistent commercial engine accepts an `evidence_gate` dependency. When supplied, every assessment must pass `require_accepted` before it can become `QUALIFIED`. A missing, pending, rejected, mismatched, or integrity-failed evidence reference results in `NEEDS_REVIEW`. Existing commercial records that use source URLs as evidence references are not silently upgraded or treated as reviewed; they remain blocked by the gate until evidence is recaptured and reviewed.

## Remaining integration gates

1. Make evidence references immutable after capture or introduce explicit superseding evidence.
2. Add source-specific capture adapters only after confirming permitted access and retention terms.
3. Add production identity integration, session revocation, and phishing-resistant MFA.
4. Add independent customer, contract, and payment verification. Owner-reviewed listing evidence is not settlement evidence.

## Immunefi source identity and change tracking

The Immunefi adapter uses `immunefi:<slug>` as its stable source key and a deterministic UUID derived from the canonical program URL as the opportunity ID. Its semantic fingerprint excludes only the observation timestamp. Re-fetching unchanged program terms therefore creates no duplicate evidence. Changes to rewards, assets, eligibility flags, scope, rules, or other captured terms create a new immutable PENDING evidence version under the same opportunity ID. Paused, invite-only, not-yet-launched, and ended listings update the latest lifecycle state only when the source was previously discovered as active. A listing first seen while inactive is not promoted into the opportunity registry.

The source observation table stores the latest lifecycle state, not a full lifecycle transition journal. Evidence versions and their capture/review events remain independently hash-verifiable.

## CLI and scheduled intake

Install the project in its virtual environment and run `ownera discover-immunefi --database /var/lib/ownera/ownera.sqlite3 --format json`. The default database path can be overridden with `OWNERA_DB_PATH`. `python -m ownera` is also supported. The command requires no API key and performs only one public catalog GET plus local SQLite writes.

`deploy/systemd/ownera-immunefi.service` runs the intake as the dedicated unprivileged `ownera` account with a read-only filesystem except `/var/lib/ownera`. `deploy/systemd/ownera-immunefi.timer` schedules one run daily at 06:30 UTC with a five-minute randomized delay. It does not scan targets, submit reports, send messages, spend funds, or execute financial actions.
