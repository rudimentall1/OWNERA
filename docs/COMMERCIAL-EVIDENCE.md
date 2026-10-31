# Commercial Opportunity Evidence Registry

**Status:** SQLite evidence capture, owner review, integrity verification, and an optional fail-closed gate in persistent commercial qualification are implemented. The gate is enforced when `PersistentCommercialEngine` is constructed with the registry; legacy callers that omit the gate retain the previous behavior.  
**Code:** `ownera/evidence_registry.py`  
**Tests:** `tests/test_evidence_registry.py`

## Purpose

The registry turns an opportunity's source material into a durable reviewable record:

1. Capture a public HTTPS source URL and bounded content snapshot.
2. Calculate and store a SHA-256 digest of the exact snapshot.
3. Create an immutable-in-normal-use evidence record in `PENDING`.
4. Require an authenticated principal with `owner:commercial` to accept or reject it.
5. Record reviewer identity from the verified principal, never from request input.
6. Verify the content digest and per-evidence hash-chained audit events.

## Trust boundaries

- HTTPS confirms transport encryption to the endpoint, not that the listing is genuine.
- A content hash detects changes to the stored snapshot; it does not prove that the source told the truth.
- A source URL, captured text, bounty listing, budget, or customer claim is untrusted until reviewed.
- Owner acceptance means the owner reviewed the captured evidence. It is not proof of customer identity, legal eligibility, an enforceable contract, or payment.
- The registry uses a single-node SQLite database. Its hash chain is tamper-evident, not tamper-proof against an attacker who can rewrite the database and recompute all hashes.
- Snapshots are limited to 16,384 characters. Adapters must avoid secrets and unnecessary personal data.

## API

- `capture(...)` stores a PENDING evidence snapshot and a capture event atomically.
- `review(credential, evidence_id, accept=...)` authenticates the owner, derives the reviewer from the principal, and stores the decision and event atomically.
- `require_accepted(opportunity_id, evidence_refs)` fails closed unless every reference is a registry UUID, belongs to the same opportunity, is ACCEPTED, and still matches its content digest.
- `verify(evidence_id)` checks the content digest and event hash chain.

The persistent commercial engine accepts an `evidence_gate` dependency. When supplied, every assessment must pass `require_accepted` before it can become `QUALIFIED`. A missing, pending, rejected, mismatched, or integrity-failed evidence reference results in `NEEDS_REVIEW`. Existing commercial records that use source URLs as evidence references are not silently upgraded or treated as reviewed; they remain blocked by the gate until evidence is recaptured and reviewed.

## Remaining integration gates

1. Make evidence references immutable after capture or introduce explicit superseding evidence.
2. Add source-specific capture adapters only after confirming permitted access and retention terms.
3. Add production identity integration, session revocation, and phishing-resistant MFA.
4. Add independent customer, contract, and payment verification. Owner-reviewed listing evidence is not settlement evidence.
