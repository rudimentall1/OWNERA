# OWNERA

### Autonomous Personal Treasury for Humans and AI

OWNERA is an owner-directed autonomous treasury and agent operating system designed to protect, manage, and grow its owner's wealth across fiat, crypto, DeFi, and traditional investments.

> **Your AI. Your Money. Your Rules.**

## Vision

OWNERA is being built toward a future where a person can delegate financial operations and bounded real-world work to a trusted autonomous system. It should manage obligations and capital, monitor markets, discover opportunities, coordinate specialized agents, earn revenue through approved services, acquire permitted infrastructure, and continuously protect the owner's financial interests.

The long-term goal is an owner-controlled agent operation that can find useful work, deliver measurable value, verify receipts, manage a capped operating budget, and report realized results. This is a development objective, not a claim of guaranteed passive income or profitability.

The agent is powerful by design, but its authority and execution are constrained by deterministic security and policy controls.

See [Worker Runtime Isolation](docs/WORKER-RUNTIME-ISOLATION.md) for the opt-in digest-pinned Docker execution boundary and real-container acceptance workflow. See [Resource Autonomy](docs/RESOURCE-AUTONOMY.md) for the Resource Autonomy Engine direction, [Commercial Engine](docs/COMMERCIAL-ENGINE.md) for opportunity qualification and owner-approved proposals, [Commercial Persistence](docs/COMMERCIAL-PERSISTENCE.md) for durable commercial pipeline recovery, [Order-to-Workforce Handoff](docs/ORDER-HANDOFF.md) for customer-approved order conversion, [Persistent Core](docs/PERSISTENT-CORE.md) for durable event storage, [Workforce Persistence](docs/WORKFORCE-PERSISTENCE.md) for versioned workforce snapshots and recovery, [Workforce Engine](docs/WORKFORCE-ENGINE.md) for task coordination, and [Resource Intelligence research](docs/RESOURCE-INTELLIGENCE-MARKET-RESEARCH.md) for the unclaimed-resource market investigation.

## Core Principles

1. **Owner First** — the owner is the sole beneficiary of the system.
2. **Agentic, not blind** — agents can reason, discover opportunities, and act within explicitly delegated scopes.
3. **Defense in depth** — no single LLM decision should be sufficient to move meaningful capital or create a binding obligation.
4. **Sovereign Reserve** — an owner-controlled reserve remains outside agent withdrawal, transfer, pledge, and reconfiguration authority.
5. **Auditable by default** — decisions, policies, opportunities, work, transactions, and outcomes should be traceable.
6. **Security before autonomy** — autonomy expands only when the corresponding security guarantees exist.
7. **Verified economics** — count received resources and realized net outcomes, not proposals, invoices, backtests, or projected returns.
8. **Future-proof cryptography** — the architecture should support migration toward post-quantum authorization without redesigning the whole treasury.

## Target Architecture

```text
                              OWNER
                                |
                       Goals / Constitution
                                |
                                v
                    COORDINATOR + AGENT FARM
                                |
                  Research / Work / Opportunity
                                |
                                v
                  RESOURCE AUTONOMY ENGINE
              Discover / Evaluate / Apply / Earn
                                |
                     Untrusted Proposals
                                |
                                v
                    OWNERA POLICY + RISK
                                |
                       Authorization Gate
                                |
                   +------------+------------+
                   |                         |
                   v                         v
             OPERATING BUDGET         OWNER TREASURY
                   |                         |
             Approved Costs            Capital / Payments
                   |                         |
                   +------------+------------+
                                |
                         AUDIT + EVIDENCE

                    SOVEREIGN RESERVE
              Owner-controlled, agent cannot withdraw
```

## Planned Modules

- `agent/` — autonomous reasoning, planning, coordination, and bounded task execution
- `constitution/` — owner goals, principles, permissions, and immutable safety rules
- `policy/` — deterministic authorization policies, commitments, and spending limits
- `risk/` — transaction, counterparty, protocol, liquidity, market, and operational risk evaluation
- `firewall/` — final pre-execution security gate
- `wallet/` — smart-account and transaction abstraction
- `payments/` — fiat, crypto, bills, subscriptions, and contact payments
- `investments/` — portfolio research, allocation proposals, and policy-bounded rebalancing
- `defi/` — protocol discovery, yield analysis, monitoring, and position management
- `treasury/` — unified balance sheet, cash flow, liabilities, and capital allocation
- `reserve/` — Sovereign Reserve with owner-only withdrawal semantics
- `resource_autonomy/` — resource discovery, eligibility, opportunity evaluation, acquisition workflows, and resource accounting
- `workforce/` — agent registry, task delegation, scoped tools, delivery review, and performance measurement
- `connectors/` — external banks, brokers, chains, protocols, marketplaces, cloud providers, and data sources
- `identity/` — owner identity, authentication, and delegation
- `voice/` — voice command interface
- `audit/` — append-only decision, opportunity, task, transaction, and outcome evidence
- `recovery/` — emergency controls, key recovery, and incident response
- `crypto/` — cryptographic providers, including future post-quantum support

These are target module boundaries, not a claim that every module exists today.

## Security Model

OWNERA explicitly separates **reasoning**, **authorization**, and **execution**.

Agents and external providers may discover opportunities, prepare plans, perform bounded work, and propose actions. They do not directly control private keys or bypass policy enforcement.

The financial execution path is intended to be:

```text
Agent proposal
   |
Intent normalization
   |
Policy validation
   |
Risk analysis
   |
Transaction / commitment checks
   |
Deterministic authorization
   |
Scoped signer or executor
   |
External system
   |
Independent verification and reconciliation
   |
Audit evidence
```

The same principle applies to resource acquisition. Discovering an unused account, wallet, server, credit, or budget does not grant permission to use it. OWNERA must establish ownership, eligibility, terms, and authorization before acquisition or use.

The Sovereign Reserve is a separate trust domain. Agents may contribute to it only through permitted flows; they cannot withdraw, transfer, pledge, or alter its protection rules.

## Status

**Stage: Architecture / Foundation**

The repository contains foundational domain and policy interfaces, sandbox financial flows, audit and reserve boundaries, an autonomous treasury decision cycle, a proposal-only external strategy protocol, a deterministic workforce coordination core with independent review gates, a commercial qualification pipeline with conservative economics and owner approval, and an order handoff bridge for customer-accepted work. Workforce transitions and commercial opportunity, assessment, proposal and approval state now have file-backed SQLite snapshot persistence with optimistic version checks and integrity digests. Order handoff persists the task graph and order idempotency record in one SQLite transaction. These are MVP persistence primitives, not a production distributed system. A digest-pinned Docker worker runtime now provides an opt-in isolated execution adapter with network isolation, read-only inputs, tmpfs workspace, and resource limits. A manually triggered real-container acceptance workflow and adversarial boundary tests are available, but have not yet been run against a reviewed image. The runtime is not yet connected to task transitions or deployed on a hardened runner. Production identity integration, customer acceptance/contract verification, adversarial runtime validation, permitted marketplace connectors, outbound proposal submission, settlement reconciliation, real financial rails, and autonomous resource acquisition remain unimplemented. CI validation is tracked in GitHub Actions.

## Roadmap

The detailed implementation order is tracked in [docs/ROADMAP.md](docs/ROADMAP.md). The Resource Autonomy direction and staged agent-farm plan are defined in [docs/RESOURCE-AUTONOMY.md](docs/RESOURCE-AUTONOMY.md).

## Non-Goals

OWNERA will not give a language model unrestricted access to production private keys, owner funds, third-party resources, or binding financial authority. Inactivity is not abandonment. Real-money autonomy and external commitments will be introduced only after ownership, authorization, recovery, security, and operational controls are implemented and tested.

## License

TBD.
