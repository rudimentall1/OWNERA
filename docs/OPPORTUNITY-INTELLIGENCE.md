# OWNERA Opportunity Intelligence

## Purpose

Turn captured public bounty listings into a small, explainable research queue. The first adapter is read-only and consumes the local Immunefi evidence registry.

## Free gig discovery

A second, read-only adapter consumes the public [OpenRadar guest feed](https://openradar.fun/v2/feed). It requests `type=gig` only, stores immutable source snapshots in the same SQLite evidence registry, and deduplicates repeated records. The guest feed is delayed by 12 hours and hides contact details, so every imported item is `OBSERVED` / `source_status=UNKNOWN`. It is not marked open merely because it appears in the feed. The original marketplace page must be checked before a lead can become actionable.

The deterministic OWNERA relevance score measures overlap with Python/backend, Telegram, deployment, Web3/security, API integration, and parsing capabilities. It is not an AI quality score, buyer verification, win probability, expected payment, or revenue. Seller offers, advertisements, vacancies and buyer requests still need manual separation.

```bash
ownera discover-openradar --limit 100
ownera discover-openradar --limit 200 --format json
```

The public guest feed hides contacts. The adapter never attempts login, contact extraction, bidding, or messaging.

## Command

```bash
ownera rank-immunefi --limit 10
ownera rank-immunefi --format json
```

The command reads the evidence database and does not mutate it, contact programs, scan assets, submit reports, or move funds.

## Score meaning

The 0-100 score is a **research-fit triage heuristic**, not probability of finding a vulnerability, probability of winning, eligibility, expected payout, or revenue forecast. It rewards public active programs, Solidity and EVM fit, source repository references, a manageable catalog asset count, smart-contract scope, and useful program context. KYC is a small friction penalty, not an automatic exclusion. Paused and invite-only listings are blocked from the research queue.

The maximum bounty ceiling is displayed only as source context and is never used in the score or treated as expected revenue. Catalog reward tiers are often incomplete. Manual review must establish current program rules, eligibility, scope, source revision, payout terms, and permitted testing methods before any research begins.

## Safety boundary

This is prioritization only. It does not authorize testing. Any later technical work must remain within the program's current written scope, avoid production-impacting tests, use local forks or controlled test environments where possible, and require owner review before report submission.

## Calibration

Record outcomes for every researched candidate: hours spent, confirmed in-scope findings, valid submissions, accepted/rejected decisions, awarded and settled amounts, and actual costs. Do not tune score weights against imagined payout. Recalibrate only from observed outcomes.
