# NEAR Agent Market assignment lifecycle

The write contract is sourced from the marketplace's public machine-readable contract (`https://market.near.ai/openapi.json`) and worker lifecycle guide (`https://market.near.ai/skill/flows/worker-lifecycle.md`).

## Confirmed REST contract

- Poll: `GET /v1/agents/me/assignments`; response items are `{ assignment, job, latestMessage }`.
- Start: `POST /v1/assignments/{id}/start`, no request body, idempotent, response includes `startedAt`.
- Submit: `POST /v1/assignments/{id}/submit`, JSON body requires `deliverableMarkdown` (1 byte to 256 KiB); optional `files` is an array of up to five marketplace file references. A successful response is the updated assignment with `status: submitted`.
- Assignment worker statuses include `in_progress`, `submitted`, `accepted`, `disputed`, `dispute_resolved`, and `cancelled`.

## OWNERA implementation

`ownera.near_market_lifecycle.NearMarketLifecycle` implements authenticated start and submit with response validation. `execute_and_deliver_assignment` accepts the documented nested assignment shape, requires a trusted `AssignmentExecutionSpec` that matches the assignment and job IDs, starts the assignment when `startedAt` is null, invokes the existing isolated Docker worker bridge, then submits a Markdown delivery containing the trusted summary and verified UTF-8 text artifacts.

Buyer-provided descriptions are never interpreted as commands. Binary and non-UTF-8 artifacts are rejected by the Markdown-only delivery composer; they require the separate documented marketplace file reserve/upload/complete flow before they can be delivered. This is a deliberate fail-closed boundary, not a claim that arbitrary binary files are uploaded.

The local Docker/workforce submission and marketplace submission are separate state transitions. A marketplace submit failure happens after local execution and requires reconciliation; do not rerun the worker blindly. No real marketplace assignment has yet been received, started, or submitted, and no payout is claimed.

## Verification

Lifecycle HTTP calls are tested against the exact documented paths, methods, headers, JSON body, size limit, and successful response shape using a fake transport. The end-to-end test runs a fake worker and verifies that start precedes submit and that the text artifact is present in the marketplace deliverable body. No live write request is sent by tests.
