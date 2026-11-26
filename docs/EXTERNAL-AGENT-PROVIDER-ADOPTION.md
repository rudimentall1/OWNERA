# External Agent Provider Adoption Decision

**Decision date:** 2026-11-26  
**Status:** Adopt provider adapters; do not replace OWNERA's control plane.

## Why this decision exists

OWNERA already has a deterministic workforce contract, durable task state, artifact evidence, independent review, and a digest-pinned Docker execution adapter. It does **not** yet have a production LLM worker/provider connected to that lifecycle. Rebuilding every specialist agent inside OWNERA would duplicate mature external projects and delay delivery.

OWNERA remains the system of record for:
- owner identity, task authorization, budgets, and approvals;
- task lifecycle, idempotency, dependencies, and deadlines;
- provider selection and capability mapping;
- evidence/artifact registration and independent QA;
- commercial acceptance, settlement, and realized economics.

External projects are replaceable execution providers. They do not become the OWNERA coordinator or receive OWNERA treasury authority.

## Provider findings

### 1. OpenHands Software Agent SDK — first coding-worker candidate

Repository: https://github.com/OpenHands/software-agent-sdk  
License: verify the exact license and dependency notices at the pinned commit before bundling or redistribution.

What is verified from the upstream README:
- Python, TypeScript, and REST APIs for software-engineering agents.
- Agent Server supports ephemeral workspaces, including Docker/Kubernetes.
- The project owns agent conversations, tools, workspaces, events, REST/WebSocket API, and typed clients.
- The upstream architecture separates execution (SDK/Agent Server) from scheduling/dispatch (OpenHands Automation).
- The upstream project is actively maintained; the inspected history included release v1.64.1 and commits on 2026-11-25.

Fit for OWNERA:
- Use it as a **specialist coding worker provider** for bounded Python/FastAPI, repository maintenance, tests, and code review preparation.
- Dispatch only tasks already authorized and scoped by OWNERA.
- Give each run a disposable workspace and narrowly scoped repository credentials, never OWNERA host credentials, wallet keys, or general server access.
- Import output as untrusted artifacts; OWNERA independently runs tests, scans diffs, and reviews acceptance criteria.

Not established yet:
- No OWNERA integration has been implemented or tested.
- Upstream SDK/Agent Server API compatibility, authentication, cancellation, artifact export, cost reporting, and sandbox configuration still require a pinned-version integration spike.
- OpenHands is a software-engineering runtime, not a universal business-agent farm and not proof of autonomous profitability.

### 2. Hummingbot Condor + Hummingbot API — specialist trading provider

Repositories:
- https://github.com/hummingbot/condor
- https://github.com/hummingbot/hummingbot-api

What is verified from upstream documentation:
- Condor is an open-source harness for autonomous trading agents.
- It separates LLM-driven market reasoning from deterministic Hummingbot API execution.
- Hummingbot API provides market data, account/position access, order execution, bot management, and DEX Gateway connectivity.
- Condor supports multiple agents and bot instances; Hummingbot documents use across 50+ exchanges/blockchains.

Fit for OWNERA:
- Keep Condor as a **separate trading vertical/provider**, not the general OWNERA worker runtime.
- OWNERA may later submit a bounded research or strategy-evaluation task to Condor and receive a signed/structured report.
- Live trading remains outside the initial integration. Any later execution must be separately authorized through OWNERA policy, with isolated credentials, hard limits, and independent reconciliation.

Known security constraint:
- Condor's local dashboard mode has no login and relies on loopback binding by default. Do not expose it publicly without an authenticated private access layer.
- Trading results and short competitions are not evidence of durable profitability.

### 3. Euron Open AgentOS — do not adopt yet

Repository: https://github.com/euron-sde-team/euron-open-agent-os

Its README claims a broad self-hosted agent runtime with team orchestration, hard budgets, approvals, checkpointing, sandboxing, REST/Python SDK, dashboard, and MIT licensing. These features are attractive on paper.

However, the inspected GitHub commit history contains a material provenance warning: on 2026-11-03, commits explicitly state that the README, architecture documents, diagrams, screenshots, and QA scripts were rewritten because they still described a different reference project named DataQuality. That does not prove the current implementation is defective, but it means README feature counts and demo claims are not sufficient evidence of maturity.

Decision: **not selected for OWNERA** until source-level audit, clean reproducible installation, license/dependency review, security review, and independent tests confirm the advertised features. Do not make it the core or replace OWNERA's workforce with it.

## Fixed provider architecture

```text
                    OWNER / OWNERA API
                            |
                  OWNERA Task + Policy Core
                            |
              validated, budgeted task envelope
                            |
                    Provider Registry
             +--------------+--------------+
             |              |              |
          OpenHands       Condor       Docker Worker
          coding          trading      deterministic
             |              |              |
             +--------------+--------------+
                            |
                   Untrusted result bundle
                            |
             OWNERA Artifact / Evidence Registry
                            |
                 Independent Quality Gate
                            |
                   ACCEPT / REWORK / REJECT
                            |
                  Commercial / Audit Ledger
```

The provider interface must be capability-oriented, not role-name-oriented. A worker is eligible only when its declared capabilities cover the task requirements. Provider output must normalize to:
- provider ID and pinned provider version;
- external run/conversation ID;
- task ID and idempotency key;
- terminal status and timestamps;
- bounded text summary;
- content-addressed artifact references and SHA-256 digests;
- measured model/tool/compute cost when available;
- structured failure/cancellation reason.

The external provider must never mark a task ACCEPTED. Only OWNERA's independent reviewer can do that.

## Integration order — fixed

1. **OpenHands coding adapter:** pin one upstream release; implement submit/poll/cancel/result retrieval; map its result into OWNERA's existing worker artifact registry. Keep credentials and workspace isolated.
2. **Contract tests:** prove idempotent submission, timeout, cancellation, provider outage, oversized output, missing artifact, digest mismatch, and retry behavior using a local mock Agent Server or deterministic fake.
3. **One real coding task:** execute a small repository task in a disposable OpenHands workspace; import the diff and test output; run OWNERA's own checks and independent review.
4. **Condor adapter:** only after the coding adapter is accepted. Begin read-only market research/dry-run; no live order authority.
5. Evaluate other providers only when a concrete task capability is missing. Do not add providers for the sake of increasing agent count.

## Non-negotiable boundaries

- No external provider can write OWNERA task state directly.
- No provider can approve its own output.
- No provider receives unrestricted host shell, Docker socket, wallet key, exchange withdrawal key, or Sovereign Reserve authority.
- Network access is denied by default and granted per provider/task only where required.
- Provider versions and container images are pinned; updates require regression tests.
- Cost ceilings are enforced by OWNERA before dispatch where possible and reconciled after execution.
- A provider's successful run is not customer acceptance or revenue.

## Evidence register

- OpenHands SDK README and architecture: https://github.com/OpenHands/software-agent-sdk
- OpenHands recent release/maintenance evidence: https://github.com/OpenHands/software-agent-sdk/commits/main
- Condor overview: https://hummingbot.org/condor/
- Condor installation and network/security notes: https://hummingbot.org/installation/condor/
- Hummingbot API responsibilities: https://hummingbot.org/hummingbot-api/
- Euron AgentOS commit history and provenance warning: https://github.com/euron-sde-team/euron-open-agent-os/commits/main

This document records a provider-adoption decision, not a claim that any external agent provider is already integrated into OWNERA.
