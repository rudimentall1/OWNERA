# NEAR Agent Market assignment lifecycle

The write contract is sourced from the marketplace's public machine-readable contract (`https://market.near.ai/openapi.json`) and worker lifecycle guide (`https://market.near.ai/skill/flows/worker-lifecycle.md`).

## Confirmed REST contract

- Poll: `GET /v1/agents/me/assignments`; response items are `{ assignment, job, latestMessage }`.
- Start: `POST /v1/assignments/{id}/start`, no request body, idempotent, response includes `startedAt`.
- Submit: `POST /v1/assignments/{id}/submit`, JSON body requires `deliverableMarkdown` (1 byte to 256 KiB); optional `files` is an array of up to five marketplace file references. A successful response is the updated assignment with `status: submitted`.
- Assignment worker statuses include `in_progress`, `submitted`, `accepted`, `disputed`, `dispute_resolved`, and `cancelled`.

## OWNERA implementation

`ownera.near_market_lifecycle.NearMarketLifecycle` implements authenticated start, file upload, assignment status reads and submit with response validation. `execute_and_deliver_assignment` accepts the documented nested assignment shape, requires a trusted `AssignmentExecutionSpec` matching assignment and job IDs, starts the assignment when `startedAt` is null, invokes the isolated Docker worker bridge, and prepares a buyer-readable Markdown result.

Every artifact is uploaded through the documented sequence: `POST /v1/files` with filename and exact byte size, `PUT` to the returned HTTPS `directUploadUrl` without forwarding the agent bearer, then authenticated `POST /v1/files/{fileId}/complete`. Returned file ID, size and SHA-256 must match before attachment. The submit body lists all uploaded file IDs; UTF-8 artifacts are also embedded in Markdown. OWNERA enforces a maximum of five files and 100 MiB combined.

A durable SQLite delivery outbox stores prepared Markdown and completed file-ID mappings. If upload preparation is interrupted, `retry_prepared_delivery` resumes from the local artifact registry without rerunning Docker. Before a submit retry, it reads `GET /v1/agents/me/assignments?status=all`; if the remote assignment is already `submitted`, it reconciles local state without a duplicate submit. If it remains `in_progress`, it sends only the marketplace submit. The `ownera-near-delivery-retry.timer` runs this delivery-only recovery every two minutes; it cannot start or rerun workers.

Buyer-provided descriptions are never interpreted as commands. A crash after remote file completion but before its file-ID mapping is committed can still create an orphan duplicate upload on retry; exactly-once upload is not claimed. No real marketplace assignment has yet been received, started, or submitted, and no payout is claimed.

## Verification

Lifecycle HTTP calls are tested against the exact documented paths, methods, headers, JSON body, size limit, and successful response shape using a fake transport. The end-to-end test runs a fake worker and verifies that start precedes submit and that the text artifact is present in the marketplace deliverable body. No live write request is sent by tests.
