# NEAR Agent Market direct-hire assignment intake

OWNERA polls the authenticated self-service endpoint `GET /v1/agents/me/assignments?status=all&limit=100&offset=...` with bounded pagination, so completed as well as active assignment statuses are visible. It persists returned assignment snapshots in `near_market_assignments` inside its operational SQLite database.

Run with the existing service credential:

```bash
set -a
. /etc/ownera/near-agent-market.env
set +a
/opt/OWNERA/.venv/bin/ownera paid-work sync-near-assignments --database /var/lib/ownera/ownera.sqlite3
```

The intake is idempotent by `assignmentId`. It records the full response snapshot and updates changed snapshots. It does not accept, start, message, submit, or otherwise mutate marketplace assignments. Assignment descriptions remain untrusted input. The execution and submission adapters exist separately, but automatic assignment planning, worker dispatch, independent review, and payout confirmation are not yet connected end to end.

The command was verified against the configured account on 2026-11-01: all-statuses endpoint returned a valid empty assignment list. No external action was performed.


## Deterministic research-plan preparation

Assignment intake also recognizes a small, explicit allowlist of NEAR research
job families currently bid by OWNERA. For a matching active assignment it stores
a deterministic plan in the near_market_assignment_plans table, including approved
primary-source URLs to open, required report sections, acceptance criteria,
word-count bounds, and a SHA-256 fingerprint of the buyer brief.

The current allowlist covers agent-to-agent commerce, recurring outsourced
tasks, specialist-agent framework integrations, distribution channels,
completed-jobs metrics, micro-job economics, and the SageKai directory lookup.
Unknown task titles are not planned. A changed brief changes the plan digest.

This is deliberately PLAN_READY_NOT_EXECUTABLE: the planner does not execute
buyer text, fetch arbitrary URLs, start assignments, submit deliverables, or
claim that source verification or independent semantic review has happened.
The assignment poll can prepare the plan as soon as a supported award appears;
the source-fetcher, report-generation, and independent-review worker remain
separate implementation gates.

## Bounded public-source collection

The collect-near-research worker runs from a one-minute systemd timer and only
considers assignments whose locally synced marketplace status is in_progress.
It re-derives the research plan from the stored original marketplace payload and
requires an exact plan match before opening any source. This prevents a modified
plan row from adding arbitrary destinations.

The collector fetches only exact URLs from the deterministic plan and only
allowlisted HTTPS hosts, rejects non-public DNS answers, restricts redirects to
the plan's approved hosts, enforces a 1.5 MB response limit and a 15-second
request timeout, and extracts HTML, JSON, or plain text. Source bytes and their
SHA-256 hashes are stored in the content-addressed artifact registry. A
SOURCE_COLLECTION.md packet records the captured pages, timestamps, hashes,
and failures.

This stage is SOURCE_COLLECTION_ONLY. It does not interpret page text as
instructions, create factual conclusions, claim semantic review, start an
assignment, or submit a marketplace deliverable. The report synthesis and
independent review stages remain separate gates.

The collector also checks each source host's robots.txt before retrieval. A
disallowed path or an unavailable robots policy fails closed for that source.
Its systemd service and timer are versioned under deploy/systemd.
