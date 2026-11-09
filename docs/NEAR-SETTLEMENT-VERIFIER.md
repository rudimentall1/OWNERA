# NEAR NEP-141 Settlement Verification

## Scope

This module verifies a NEP-141 payout transaction using the NEAR JSON-RPC
`EXPERIMENTAL_tx_status` method. It is read-only: it never signs, submits, or
moves funds. It is intended as the first provider-specific verification adapter
for the OWNERA settlement ledger.

## Verification contract

The caller must supply values bound to a canonical accepted order and payout
record:

- transaction hash;
- transaction signer account ID (required by the NEAR RPC lookup);
- NEP-141 token contract;
- expected recipient account ID;
- expected payout amount in atomic token units;
- expected transfer sender account ID, when known.

The verifier checks that:

1. the RPC response identifies the requested transaction and signer;
2. the final transaction status is successful;
3. a successful receipt was executed by the expected token contract;
4. the receipt contains a NEP-141 `ft_transfer` event;
5. the recipient and, when supplied, sender match exactly;
6. the sum of matching transfer events equals the expected atomic amount;
7. the response digest and receipt/block references are returned as evidence.

The caller must not calculate the expected amount from a hard-coded marketplace
fee. The accepted bid, the fee in effect at hire, payout currency, and actual
payout terms must come from the canonical job/marketplace record. The current
NEAR Agent Market terms describe a 5% platform fee, but also state that the fee
is fixed at hire and may change for future jobs.

## Trust boundary and limitations

The result is labelled `NEAR_RPC_VERIFIED`, not `TRUSTLESS_VERIFIED`. The
verifier trusts the configured HTTPS RPC endpoint to return authentic chain
state. It hashes the returned RPC result for reproducible evidence but does not
independently verify the Merkle proof against a trusted block header.

This adapter covers NEP-141 on NEAR only. It does not verify USD/Stripe payouts,
USDC held in a third-party wallet provider on another chain, withdrawals to a
bank, refunds, chargebacks, or final spendable balance. A successful payout
transfer is not proof that funds remain available after later reversals or
withdrawals.

The verifier is not yet wired into `SQLiteSettlementLedger`; existing ledger
records remain `OWNER_ATTESTED` unless and until a separate integration changes
the persisted verification level and adds end-to-end reconciliation tests.

## Tests

`tests/test_near_settlement.py` covers successful payout parsing, wrong signer,
wrong token contract, wrong recipient, amount mismatch, failed transaction,
missing transfer event, RPC error, and invalid input. Tests use a deterministic
mock RPC response and make no live network calls.

## Next integration gate

Bind this verifier to canonical marketplace settlement evidence and the
accepted order record. Persist the verified transaction reference and evidence
digest in the settlement ledger using a distinct verification level. Add tests
for idempotency, replay, duplicate transaction references, partial payouts,
refunds/reversals, and exact order-to-payout amount reconciliation before
counting any amount as realized net revenue.
