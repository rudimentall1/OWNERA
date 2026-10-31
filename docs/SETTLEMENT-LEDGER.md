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

## What this does not prove

An owner-attested record is not independent proof that money reached a bank
account, wallet, or payment processor. The digest proves neither authenticity
nor truth of the underlying evidence. There is no payment-provider webhook,
bank connector, on-chain transaction verifier, invoice lifecycle, refund or
chargeback model, or automatic reconciliation yet. Do not report these records
as independently verified revenue.

The event chain is tamper-evident, not tamper-proof. This first increment does
not yet reconcile the receipt table against event payloads after database-level
tampering. It is a local, single-node SQLite ledger, not a distributed
accounting system.

## Next acceptance boundary

Add reconciliation that compares every receipt row with its corresponding
event, then add one real payment rail adapter with signature verification and
replay protection. Only provider-verified or independently confirmed on-chain
receipts should qualify as verified settlement.
