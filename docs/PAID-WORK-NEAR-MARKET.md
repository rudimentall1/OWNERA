# NEAR Agent Market intake

`ownera paid-work sync-near-market` polls the authenticated builder endpoint `GET /v1/jobs/board?kind=standard` and imports public `open` and `filling` standard jobs into the existing Paid Work commercial store.

The adapter is read-only toward the marketplace. It does not bid, message buyers, accept assignments, start work, submit deliverables, or move funds. Job descriptions and tags are untrusted input. Imported records remain `DISCOVERED`; qualification still requires economics, terms, and eligibility review.

The job ID is mapped to a stable OWNERA UUID. Explicit reject-test listings are ignored. Capability hints are derived from title and tags rather than arbitrary description text. Repeated unchanged records are idempotent. If title, description, budget, or currency changes, the adapter reports a conflict and preserves the existing record rather than silently overwriting it. USDC is retained as a four-character currency code.

Configure `NEAR_AGENT_MARKET_API_TOKEN` in the process environment (the server deployment keeps it in `/etc/ownera/near-agent-market.env`, mode 0600), then run:

```bash
ownera paid-work sync-near-market
ownera paid-work list
```

No token value should be printed or committed. This command currently performs one board snapshot per invocation; scheduling and bid submission are separate, not yet enabled.

## Server polling

The server runs `ownera-near-market-sync.timer` every five minutes. Its oneshot service reads the token from `/etc/ownera/near-agent-market.env` and writes only to `/var/lib/ownera`. It has no marketplace write calls. Check it with:

```bash
systemctl status ownera-near-market-sync.timer
journalctl -u ownera-near-market-sync.service -n 30 --no-pager
```

A successful poll means only that the board was captured. It is not a bid, hire, completed assignment, or revenue.
