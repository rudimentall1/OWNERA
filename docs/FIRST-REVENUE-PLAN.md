# OWNERA First Revenue Plan

**Objective:** obtain and verify the first real customer payment. This is an execution target, not a revenue forecast or guarantee.

## Current truth

- OWNERA has not recorded any realized revenue.
- The Immunefi adapter has captured 148 active public listings.
- `rank-immunefi` now produces an explainable research-fit shortlist. It does not estimate exploit probability or expected payout.
- One Charm callback-trust hypothesis was reproduced only in a local harness and closed as not reportable because a realistic in-scope victim path was not established.
- The commercial engine and durable persistence exist, but no live paid-work source connector or active customer order is currently connected.

## Priority order

### 1. Paid work: primary first-revenue channel

Target one small, fixed-scope service that can be delivered with existing capabilities: Python/FastAPI backend work, Telegram or AI-agent automation, or a bounded Web3 integration. Do not market a broad "AI agent development" promise. Sell a concrete deliverable with acceptance tests, a deadline, exclusions, and a fixed price.

Workflow:

1. Capture a current listing or direct customer request with source evidence.
2. Confirm budget, scope, deadline, platform fees, eligibility, and acceptance criteria.
3. Estimate delivery hours and direct costs conservatively.
4. Reject work with unclear requirements, negative net economics, or unreasonable deadlines.
5. Draft a tailored proposal for owner review.
6. Submit only after explicit owner approval.
7. Deliver through a bounded task plan and independent QA.
8. Count revenue only after payment is received and reconciled against fees and actual costs.

### 2. Bug bounty: secondary, high-variance channel

Continue monitoring and qualifying programs, but do not treat maximum bounty ceilings as expected income. Research remains local-only unless the program explicitly permits the exact activity. Every report needs a reproducible PoC and owner review. A bounty is revenue only after a reward is confirmed and paid.

## 30-day execution target

- **Days 1-3:** choose one service, define its fixed scope, price floor, delivery time, exclusions, and a small proof sample.
- **Days 4-7:** review current paid requests from permitted sources and prepare a small number of highly tailored proposals.
- **Week 2:** secure one bounded order or revise the offer based on real buyer feedback.
- **Weeks 2-3:** deliver, pass independent QA, obtain customer acceptance, and collect payment.
- **Week 4:** reconcile actual net profit, record conversion and delivery data, and repeat the best-performing offer.

A first payment within 30 days is the target, not a promise. If no qualified buyer responds, change the offer or channel based on observed feedback rather than adding more infrastructure.

## OWNERA build priorities

1. Manual-first paid-work intake with evidence capture.
2. Persistent qualification using conservative budget floor, delivery cost, platform fee, contingency, and explicit win-probability input.
3. Proposal templates with scope, exclusions, acceptance criteria, milestones, and delivery plan.
4. Owner approval and idempotent submission record. No autonomous outreach or commitments.
5. Customer acceptance, workforce handoff, independent QA, and payment reconciliation.
6. Only then consider permitted marketplace connectors and more autonomy.

## Success definition

The first-revenue milestone is complete only when a real customer order has been accepted, delivered, independently reviewed, paid, and reconciled. A listing, proposal, award notice, invoice, simulated balance, or projected payout does not count.

## Paid-work implementation update (2026-11-01)

A manual-first CLI now sits on the existing persistent Commercial Engine:

- `ownera paid-work ingest` captures a listing with source URL, budget range, required capabilities, and evidence references. IDs are deterministic by source URL and identical re-imports are idempotent.
- `ownera paid-work list` displays the durable opportunity queue.
- `ownera paid-work assess` calculates conservative economics from the budget floor and requires explicit manual terms/eligibility flags to qualify.
- `ownera paid-work draft` creates an owner-reviewable proposal draft for a qualified opportunity. It does not send the proposal.

This closes the first local intake-to-proposal workflow, but it does not yet provide automatic marketplace discovery, external submission, or worker execution. The next proof is to process a real current lead from the user's marketplace profile or an allowed public source and prepare one tailored proposal for owner approval.
