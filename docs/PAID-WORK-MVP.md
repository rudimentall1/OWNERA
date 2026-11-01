# OWNERA Paid Work MVP

**Status:** Manual-first intake, persistent qualification, and proposal drafting are implemented. Marketplace discovery connectors, outbound proposal submission, customer contract verification, automated task execution orchestration, delivery acceptance, and payment reconciliation are not yet connected.

## Objective

Get the first paid customer order through a controlled process using the existing Commercial Engine and Workforce Engine. The first release optimizes for a real order, not autonomous browsing or a large agent count.

## Initial service focus

Keep the offer narrow and based on capabilities already available:

1. Python and FastAPI bug fixes, endpoints, API integrations, and small backend tasks.
2. Telegram bot development, maintenance, and API automation.
3. Docker, Linux, Nginx deployment fixes and operational automation.
4. Web3 RPC integrations, monitoring scripts, and controlled smart-contract testing.

Do not sell broad, undefined "AI agent development". Each offer must have a bounded scope, explicit exclusions, acceptance criteria, a delivery plan, and a fixed quote.

## Current CLI

The paid-work commands use the existing SQLite commercial snapshot and append-only event log.

### 1. Capture a listing manually

Save a source-backed listing as JSON. Example:

```json
{
  "title": "Build a Telegram notification bot",
  "description": "Create a small Python bot that posts alerts from a public API.",
  "source_name": "Kwork",
  "source_url": "https://kwork.ru/projects/987654",
  "budget_min": "12000",
  "budget_max": "18000",
  "currency": "RUB",
  "required_capabilities": ["python", "telegram", "api_integration"],
  "evidence_refs": ["https://kwork.ru/projects/987654"]
}
```

Then run:

```bash
ownera paid-work ingest --payload-file listing.json
ownera paid-work list
```

The opportunity ID is deterministic from the source URL. Re-importing the same listing is idempotent. Reusing the source URL with changed terms fails closed instead of overwriting the original record. Update terms only through a deliberate review workflow.

### 2. Assess the economics

```bash
ownera paid-work assess \
  --opportunity-id <UUID_FROM_INGEST> \
  --delivery-cost 5000 \
  --platform-fee-rate 0.10 \
  --contingency-rate 0.10 \
  --win-probability 0.50 \
  --minimum-net-margin 0.20 \
  --terms-reviewed \
  --eligibility-confirmed
```

The calculation uses the budget floor as conservative revenue, subtracts the platform fee, estimated delivery cost, and contingency. `win_probability` is a manual assumption used only for a risk-adjusted comparison; it is not a model prediction. The flags are operator attestations, not independent verification. If terms or eligibility are not confirmed, leave the corresponding flag off and the opportunity remains `NEEDS_REVIEW`.

### 3. Draft a proposal

Create a JSON file with `opportunity_id`, `scope`, `acceptance_criteria`, `delivery_plan`, `quote_amount`, and `currency`, then run:

```bash
ownera paid-work draft --payload-file proposal.json
```

Only qualified opportunities can receive a proposal draft. The proposal remains `AWAITING_OWNER_APPROVAL`. The CLI does not send it to the customer.

## Authority boundaries

- Scout intake does not grant permission to contact a customer.
- A proposal draft is not an offer until the owner approves and manually submits it.
- Proposal approval is not customer acceptance.
- A customer acceptance is not permission to spend the full accepted amount. The owner must approve an execution budget.
- Workforce tasks must be created from the exact accepted scope through Order-to-Workforce Handoff.
- Runtime execution remains bounded and sandboxed. It must not receive platform credentials, owner secrets, wallet keys, or unrestricted host access.
- Delivery requires independent QA and owner review.
- Revenue is counted only after settlement is independently verified and reconciled against fees, compute/model costs, labor, refunds, and other direct costs.

## Discovery policy

Start with owner-provided links, manually reviewed listings, direct customer requests, and official APIs or feeds whose terms explicitly permit the intended use. Do not automate private mobile APIs, scrape authenticated pages, bypass access controls, or send unsolicited bids. A source connector is not approved until its access method, retention rules, and permitted use are documented.

## Next implementation gates

1. Run this intake and proposal workflow against real, manually captured opportunities.
2. Add a source adapter only for a permitted API/feed or owner-authorized integration.
3. Add a bounded proposal-quality worker that drafts from the captured scope and a selected service template. Owner approval remains mandatory.
4. Connect accepted orders to persistent task graphs and run one local worker execution plus independent QA.
5. Complete a real customer delivery and reconcile the actual payment.

The first success metric is one real paid order completed and paid, not the number of captured listings, generated proposals, or simulated agent runs.
