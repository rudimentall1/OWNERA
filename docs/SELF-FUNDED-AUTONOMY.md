# OWNERA Self-Funded Autonomy

**Non-negotiable constraint:** OWNERA must not require the owner to deposit money to operate its first-revenue path. The project starts with zero owner-funded operating budget. Paid infrastructure may be acquired only from independently verified revenue already earned by OWNERA.

This is an engineering and treasury policy, not a promise that agents can create money without resources. Before the first receipt, agents must use existing infrastructure, free tiers within their terms, open-source software, public data, and bounded local execution. If a task cannot be completed within those constraints, OWNERA must reject or defer it rather than ask the owner to finance it.

## 1. Capital boundaries

Maintain logically and, when real financial rails are implemented, cryptographically separate balances:

1. **Sovereign Reserve:** owner-protected capital. Agents may deposit into it. Agents may never withdraw, transfer, approve allowances against, pledge, lend, or reconfigure it.
2. **Earned Operating Treasury:** verified proceeds from completed paid work, after platform fees, refunds, direct delivery costs, and legally required reserves are accounted for. Only this balance may fund approved agent operating expenses.
3. **Pending Receipts:** awards, invoices, escrow balances, and expected payouts that have not settled. These are not spendable funds.
4. **Expense Commitments:** authorized but not yet paid operating costs. These reduce available operating balance immediately.

No balance may be inferred from an API response that merely says a job was awarded or submitted. No simulated balance, forecast, token reward estimate, or unconfirmed bounty counts as revenue.

## 2. Revenue-to-reinvestment waterfall

For every incoming payment:

1. Verify settlement independently through a trusted payment-provider event, on-chain receipt, or other approved source. Owner attestation alone is not sufficient to unlock automated spending.
2. Reconcile gross amount, currency, platform fees, refunds, chargeback exposure, and direct delivery costs.
3. Set aside tax and legal obligations using a jurisdiction-aware policy. Until this exists, do not treat the uncertain portion as free operating cash.
4. Calculate realized net proceeds.
5. Top up the Sovereign Reserve according to the owner's configured target and contribution rule. This is deposit-only for agents.
6. Move only the explicitly budgeted remainder into the Earned Operating Treasury.
7. Record every allocation with source receipt, currency, timestamp, policy version, and idempotency key.

The waterfall must be atomic or recoverable. A retry must never allocate the same receipt twice.

## 3. What agents may buy

Before there is verified revenue, only zero-cost or already-paid-for resources may be used. Agents must not create a paid subscription, cloud instance, API bill, blockchain transaction fee, or recurring commitment on the owner's behalf.

After verified revenue exists, agents may request expenses from the Earned Operating Treasury only for allowlisted categories, such as:
- compute required to deliver an accepted paid order;
- inference required to complete a qualified, profitable task;
- storage, bandwidth, and monitoring needed for delivery;
- marketplace or payment fees directly associated with earning revenue.

Every expense request must include:
- the task/order that requires it;
- provider and exact price, currency, billing period, and cancellation terms;
- expected delivery benefit and conservative net-profit calculation;
- cheaper free/local alternative considered;
- one-time versus recurring classification;
- maximum amount and expiry;
- rollback/cancellation procedure.

The policy engine must reject expenses that exceed the earned operating balance, exceed per-task or monthly caps, are not allowlisted, or would create an uncovered recurring liability. No borrowing, leverage, credit, overdrafts, reserve collateral, or owner-funded fallback is permitted.

## 4. Autonomous expense authority

Autonomy is earned in stages:

- **Stage 0, zero capital:** free/local execution only. No external paid spending.
- **Stage 1, first verified receipts:** agents may calculate and recommend expenses; no automatic payment until settlement verification and spend controls pass adversarial tests.
- **Stage 2, bounded reinvestment:** agents may pay pre-approved categories from earned operating funds within a small hard cap and per-order budget. No new recurring subscriptions.
- **Stage 3, recurring infrastructure:** permitted only after multiple successful delivery and payout cycles, cancellation tests, budget monitoring, and emergency shutdown are proven.
- **Stage 4, broader treasury autonomy:** separate review, policy limits, and external security assessment required. Sovereign Reserve remains inaccessible.

A budget is not authority to spend. Each payment still needs a task-bound authorization, idempotency protection, recipient/provider allowlisting, and an auditable receipt.

## 5. Failure and insolvency behavior

If the operating balance is insufficient, the agent must:
- stop new bids that could create unfunded delivery obligations;
- finish or safely pause already accepted work;
- use free/local alternatives where contractually acceptable;
- cancel unused paid resources;
- report the shortfall and evidence;
- never reach into the Sovereign Reserve or request an owner top-up as the default recovery path.

If a customer accepts multiple bids unexpectedly, the commitment cap must prevent accepting work beyond verified workforce capacity and available delivery resources.

## 6. Required implementation proofs

Do not call self-funding implemented until all of the following are demonstrated:

- independently verified incoming payment is recorded exactly once;
- gross-to-net reconciliation matches provider/on-chain evidence;
- reserve allocation is deposit-only and cannot be bypassed by any agent role;
- pending, disputed, refunded, or owner-attested-only receipts cannot fund expenses;
- a task-bound expense can be paid from earned funds within policy;
- attempts to exceed the balance, cap, category allowlist, or commitment window are denied;
- retry/replay cannot duplicate payments or allocations;
- recurring costs are visible, capped, and cancellable;
- insolvency stops new commitments without touching the reserve;
- complete audit trail links order, delivery, receipt, allocation, expense, and remaining balance.

Until then, OWNERA is **not self-funding yet**. This document establishes the required architecture and acceptance criteria; it does not claim the payment rails or automated spending are already live.
