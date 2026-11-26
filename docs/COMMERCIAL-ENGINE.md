# OWNERA Commercial Engine

**Status:** Deterministic qualification and proposal approval core implemented, with SQLite snapshot persistence and append-only commercial events through `PersistentCommercialEngine`. A manual-first intake/assessment/draft CLI is available through `PaidWorkPipeline`. Marketplace discovery connectors, outbound proposal submission, contract signing, customer acceptance verification, and payment processing are not implemented.
**Code:** `ownera/commercial.py`, `ownera/persistent_commercial.py`, `ownera/paid_work.py`
**Tests:** `tests/test_commercial.py`, `tests/test_paid_work.py`

## Purpose

The Commercial Engine converts a discovered paid-work listing or customer lead into a qualified commercial opportunity, then prepares a proposal draft for owner review. It is designed to feed an approved order into the Workforce Engine.

It does not autonomously contact customers, bid, sign contracts, promise delivery, accept legal obligations, or collect payment.

## Workflow

```text
DISCOVERED
   |
   v
SOURCE + EVIDENCE CHECK
   |
   v
COMMERCIAL ASSESSMENT
   |
   +---- missing terms / eligibility ----> NEEDS_REVIEW
   |
   +---- expired / uneconomic ----------> REJECTED
   |
   v
QUALIFIED
   |
   v
PROPOSAL DRAFT
   |
   v
AWAITING_OWNER_APPROVAL
   |
   v
APPROVED_FOR_SUBMISSION
   |
   | Future outbound adapter; not implemented
   v
CUSTOMER SUBMISSION / NEGOTIATION
```

Owner approval in this version records an internal approval state only. It does not submit the proposal.

## Opportunity record

Each opportunity requires:
- title and scope description;
- source name and absolute HTTP(S) source URL;
- conservative budget floor and upper bound;
- currency;
- required workforce capabilities;
- at least one evidence reference;
- discovery timestamp and optional deadline.

The evidence reference is a provenance pointer, not proof that the listing is genuine or that the customer will pay. Future source adapters must preserve source retrieval time, terms, access method and permitted-use restrictions.

## Qualification economics

The first version uses the **budget floor**, not the midpoint or maximum, as conservative revenue.

```text
platform_fee = conservative_revenue * platform_fee_rate
contingency = estimated_delivery_cost * contingency_rate
estimated_total_cost = delivery_cost + platform_fee + contingency
expected_net_profit = conservative_revenue - estimated_total_cost
expected_net_margin = expected_net_profit / conservative_revenue
risk_adjusted_value = expected_net_profit * win_probability
```

An opportunity is not qualified unless:
- the deadline has not expired;
- terms have been reviewed;
- eligibility has been confirmed;
- conservative expected net profit is positive;
- expected net margin meets the configured threshold.

Missing terms or eligibility results in `NEEDS_REVIEW`, not a positive qualification. An expired or uneconomic opportunity is rejected.

The probability is an explicit assessment input, not an AI-generated fact. The initial model is intentionally simple and should be calibrated against actual outcomes before it is used for automated ranking.

## Proposal approval

A proposal draft requires:
- scoped work description;
- acceptance criteria;
- delivery plan;
- quote and currency.

Only a qualified opportunity can receive a proposal. The quote currency must match the opportunity currency, and the quote cannot undercut the conservative budget floor in this first version.

An owner must explicitly approve the proposal before it can enter `APPROVED_FOR_SUBMISSION`. No external submission function exists yet.

## Security and commercial boundaries

1. A listing is not a verified customer or guaranteed payment.
2. Public source data must be collected and reused according to source terms and applicable law.
3. No automated bidding, outreach, negotiation, contract acceptance, or delivery commitment is enabled.
4. Owner approval is required before any external proposal submission or binding commitment.
5. Delivery budget estimates are not spending permissions. Any actual expenditure must pass OWNERA policy and budget controls.
6. Revenue is not recognized from a listing, proposal, award notice, or invoice. Only independently confirmed settlement can count as revenue.
7. The Workforce Engine receives work only after the customer order and scope are approved.

## Next gates

### 1. Source adapters

Manual-first intake is available through `ownera paid-work ingest`; the persistent qualification and proposal draft path is available through `ownera paid-work assess` and `ownera paid-work draft`. No paid-work marketplace connector is currently deployed. Add one permitted source connector only after confirming its terms and stable access method. Do not scrape behind authentication or bypass platform controls.

### 2. Real cost estimation

Use historical delivery time, model/tool usage, platform fees, revisions, taxes/withholding assumptions and refund/dispute risk. Track estimated versus actual cost per order.

### 3. Proposal quality

Add service templates with fixed scope, exclusions, milestones, delivery time, revision limits, acceptance tests and handover requirements. Human review remains mandatory.

### 4. Approved outbound adapter

Only after production owner identity, phishing-resistant authentication, policy integration, approval binding and idempotency are in place. It must submit exactly the approved proposal version and record the external response.

### 5. Order-to-workforce handoff

Convert an accepted, owner-approved customer order into a bounded task graph with capability requirements, dependencies, per-task budgets and independent QA.

## First commercial success criterion

A real customer order is sourced with evidence, assessed using conservative economics, explicitly approved by the owner, delivered by specialist workers, independently reviewed, accepted by the customer, and paid. Actual costs and settled revenue are reconciled. No simulated or projected income counts.
