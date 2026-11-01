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
