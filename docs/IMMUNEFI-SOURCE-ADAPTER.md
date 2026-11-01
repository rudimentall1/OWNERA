# Immunefi Public Catalog Intake

**Status:** Read-only discovery adapter implemented. It creates unqualified candidates and PENDING evidence records. It does not create a `CommercialOpportunity`, qualify a bounty, test an asset, or submit a vulnerability report.

**Code:** `ownera/sources/immunefi.py`  
**Tests:** `tests/test_immunefi_source.py`

## Source

The adapter reads:

`https://immunefi.com/public-api/bounties.json`

The endpoint is described by external API catalog documentation as an unauthenticated, read-only catalog containing project identifiers, reward ceilings, program types, ecosystems, languages, KYC and invite-only flags, assets, reward tiers, and rules. A third-party probe reported a successful anonymous response in August 2026. Immunefi does not publish a formal stable OpenAPI contract for this endpoint, so the adapter treats its schema as observed rather than guaranteed.

## Intake behavior

1. Fetches the catalog over HTTPS with a 20-second timeout and a 12 MiB response cap.
2. Requires JSON and validates the top-level array and fields needed to establish program identity and status.
3. Excludes paused, invite-only, future, and expired programs.
4. Retains KYC status and technical metadata for owner review.
5. Creates a new opportunity UUID and stores a bounded JSON snapshot in the evidence registry.
6. Uses the canonical program page as the evidence source URL.
7. Leaves the evidence in `PENDING`. The owner must review it before it can pass commercial qualification.

## Important economic boundary

The catalog's `maxBounty` is represented as `max_bounty_ceiling`. It is a published maximum, not a guaranteed payment, minimum budget, expected value, or revenue. The adapter deliberately does not convert it into `CommercialOpportunity.budget_min` and does not create a qualified commercial opportunity.

A bounty is not a paid work order. Actual payout depends on finding an eligible issue, complying with the program's current rules, report acceptance, severity assessment, duplicate status, and the platform's payout process. The listing snapshot is not proof that OWNERA or its operator is eligible to test a target.

## Safety and limitations

- No active scanning, exploitation, fuzzing, wallet interaction, transaction signing, or report submission occurs.
- The adapter does not interpret a listing as permission to test. The current program policy and scope must be reviewed on the official program page before any research.
- KYC requirements are recorded, not bypassed.
- The catalog schema is not a formal versioned contract. Structural drift fails closed rather than silently inventing defaults.
- The adapter captures a bounded metadata snapshot. It records whether the displayed asset and reward previews were truncated. The full current rules remain on the official program page.
- The adapter currently has no scheduler, persistent source cursor, deduplication across repeated catalog pulls, or automatic source-change monitoring.
- A fresh discovery creates a fresh candidate UUID. Cross-run deduplication and superseding evidence are follow-up work.

## Next gates

1. Add stable source identity and deduplication by platform plus slug.
2. Add source-change detection and explicit superseding evidence when program scope or rewards change.
3. Add an owner review queue that displays source, capture time, hash, assets, KYC, rules, and reward ceiling.
4. Add a second permitted source adapter only after its access contract and data-retention terms are confirmed.
5. Keep qualification, customer acceptance, work-order handoff, and settlement as separate gates.
