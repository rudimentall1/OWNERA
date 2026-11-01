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
