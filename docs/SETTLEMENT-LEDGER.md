# Owner-Attested Settlement Ledger

## Purpose

The settlement ledger records incoming receipts against an accepted order. It
keeps expected order value separate from amounts recorded as received, supports
partial receipts, prevents cumulative receipts from exceeding the accepted
amount, and persists each receipt with an append-only event in one SQLite
transaction.

## Current contract

- Each receipt is explicitly marked `OWNER_ATTESTED`.
- The caller supplies the accepted order amount and currency; repeated receipts
  for the same order must use identical terms.
- A receipt requires a payment reference and SHA-256 digest of the evidence
  material retained by the caller.
- The ledger stores the digest, not the underlying bank statement, invoice, or
  provider payload.
- Idempotency keys make retries safe and reject reuse with different data.
- Partial receipts are supported. Cumulative owner-attested receipts cannot
  exceed the accepted order amount.
- Receipt row and hash-chained event are committed atomically.
- The application-facing `OwnerSettlementControl` requires a verified principal
  with `owner:settlement`; the audit actor is derived from that principal.
- The raw ledger write method is internal and must not be exposed by an API.

## What this does not prove

An owner-attested record is not independent proof that money reached a bank
account, wallet, or payment processor. The digest proves neither authenticity
nor truth of the underlying evidence. There is no production identity provider or HTTP boundary, payment-provider
webhook, bank connector, on-chain transaction verifier, invoice lifecycle,
refund or chargeback model, or automatic reconciliation yet. The injected
authenticator is a contract; the current test authenticator is test-only. Do not report these records
as independently verified revenue.

The event chain is tamper-evident, not tamper-proof. The ledger verification
method compares each receipt row with its corresponding event and detects
row-level changes or missing/extra records. It does not protect against an
attacker who can rewrite both the database rows and the event chain. It is a
local, single-node SQLite ledger, not a distributed accounting system.

## Next acceptance boundary

Add one real payment rail adapter with signature verification and replay
protection, and reconcile provider events against this ledger. Only
provider-verified or independently confirmed on-chain receipts should qualify
as verified settlement. The accepted order amount must also be loaded from the
canonical accepted-order record rather than trusted as a caller-supplied value.
