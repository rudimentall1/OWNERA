# Commercial Persistence

## Purpose

Persist OWNERA's opportunity qualification and proposal approval pipeline across process restarts. This is the durable foundation for a commercial workflow; it is not a marketplace connector, CRM, contract system, payment processor, or revenue ledger.

## Components

- `CommercialEngine.to_snapshot()` and `from_snapshot()` serialize and restore opportunities, assessments, qualification results, proposals, and owner-approval metadata.
- `SQLiteCommercialRepository` stores a complete canonical JSON snapshot in SQLite with a monotonically increasing version and SHA-256 integrity digest. It commits the snapshot and its append-only event in the same SQLite transaction.
- `PersistentCommercialEngine` persists each successful domain transition and restores the last committed state after a stale-writer conflict or failed operation.

## Guarantees

1. File-backed SQLite is required. In-memory databases are rejected.
2. Every successful add, assessment, proposal draft, and owner approval advances the snapshot version.
3. A stale process cannot overwrite a newer snapshot. The writer receives a conflict and reloads committed state.
4. Snapshot payloads are canonicalized before hashing. A digest mismatch prevents restoration.
5. Decimal values and timestamps are serialized explicitly, avoiding float conversion for commercial amounts.
6. Restored references are checked: assessments/results must pair, and proposals must reference existing opportunities.

## Explicit limitations

- The repository stores one complete commercial snapshot. It is suitable for the current single-owner MVP, not high-throughput multi-tenant operation.
- The digest detects accidental or unauthorized payload modification when the stored digest is not also replaced. It is not a cryptographic signature or tamper-proof audit log.
- The commercial snapshot and event are transactionally coupled. Workforce and order-handoff transitions are not yet fully coupled to the event store.
- Commercial and workforce/order state are separate repository concerns. Cross-domain atomicity is currently implemented for order handoff plus workforce snapshot, not for every commercial-to-order transition.
- No source scraping, external customer messaging, proposal submission, contract signing, invoicing, payment collection, settlement verification, tax calculation, or realized P&L ledger exists.
- A proposal approval is permission to submit a proposal, not proof it was submitted, accepted, contracted, delivered, or paid.

## Verification

The test suite covers restart recovery across qualification and owner approval, stale-writer rejection and reload, snapshot digest tampering, and empty repository initialization.

## Next gates

1. Append-only commercial transition evidence with actor, timestamp, prior/new state and source references.
2. Durable customer acceptance and contract evidence before order creation.
3. Atomic commercial-order-workforce boundary, including proposal and order provenance.
4. Settlement evidence and realized cost/revenue reconciliation. Do not label an invoice or award notice as income.
