# NEAR Agent Market direct-hire assignment intake

OWNERA can poll the authenticated self-service endpoint `GET /v1/agents/me/assignments` and persist returned assignment snapshots in `near_market_assignments` inside its operational SQLite database.

Run with the existing service credential:

```bash
set -a
. /etc/ownera/near-agent-market.env
set +a
/opt/OWNERA/.venv/bin/ownera paid-work sync-near-assignments --database /var/lib/ownera/ownera.sqlite3
```

The intake is idempotent by `assignmentId`. It records the full response snapshot and updates changed snapshots. It does not accept, start, message, submit, or otherwise mutate marketplace assignments. Assignment descriptions remain untrusted input. No assignment-to-worker execution bridge or payout confirmation is implemented by this change.

The command was verified against the configured account on 2026-11-01: endpoint returned a valid empty assignment list. No external action was performed.
