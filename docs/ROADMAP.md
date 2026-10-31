# OWNERA Roadmap

The roadmap is deliberately ordered by safety. Autonomy expands only after the underlying authorization, evidence, and recovery boundaries are proven.

## 0 — Foundation

- [x] Repository foundation
- [x] Domain model
- [x] Owner Constitution
- [x] Policy/risk interfaces
- [x] Sovereign Reserve boundary
- [x] Threat model
- [x] CI
- [x] Structured audit event model
- [x] Configuration/capability model
- [ ] Formal security invariants

## 1 — Financial Sandbox

- [x] Simulated accounts
- [x] Simulated transactions
- [ ] Agent intent planner
- [x] Policy evaluation API
- [x] Risk scoring API
- [x] Idempotency / replay protection in sandbox
- [x] Daily spend limit enforcement in sandbox
- [x] Pre/post execution audit events
- [x] Recurring obligation scheduling
- [ ] Simulated bill payments
- [ ] Simulated investment allocation
- [x] Reserve accumulation simulation boundary
- [x] Initial adversarial/security tests

## 2 — Resource Discovery (read-only)

- [ ] Define canonical resource-opportunity schema and provenance
- [ ] Add approved public sources for grants, bounties, paid work, cloud credits, and compute
- [ ] Normalize, deduplicate, rank, and expire opportunities
- [ ] Check eligibility, ownership, terms, and required permissions
- [ ] Produce an evidence-backed opportunity report
- [ ] No external commitments, spending, or live financial execution in this phase

## 3 — Owner-Approved Resource Acquisition

- [ ] Application and proposal drafting
- [ ] Owner approval before submission or commitment
- [ ] Grant, bounty, customer, and infrastructure acquisition workflows
- [ ] Verify actual receipt, restrictions, and expiry
- [ ] Record costs, outcomes, and evidence

## 4 — Earned Revenue and Agent Workforce

- [x] Define initial worker/task contract and deterministic in-memory assignment/review lifecycle
- [x] Add initial SQLite append-only event store with optimistic concurrency and hash-chain verification
- [x] Add versioned SQLite workforce snapshot repository with restart recovery and digest verification
- [x] Persist workforce transitions automatically through a versioned SQLite facade
- [x] Validate and persist complete workforce task graphs as one snapshot during handoff
- [x] Persist order idempotency, proposal reference, plan digest and task graph in one SQLite transaction
- [x] Add versioned SQLite commercial snapshot repository and automatic persistence facade
- [x] Persist workforce state with restart recovery and optimistic concurrency
- [x] Integrate append-only transition evidence with the workforce repository
- [x] Define initial commercial opportunity qualification and owner-approved proposal draft lifecycle
- [x] Define customer-accepted, owner-approved order handoff into bounded workforce task graphs
- [x] Couple commercial snapshot writes with append-only hash-chained events in one SQLite transaction
- [x] Couple order-handoff persistence with append-only events in one SQLite transaction
- [x] Persist customer and owner acceptance evidence with digest binding in the order handoff transaction
- [x] Add Ed25519 customer acceptance verification against owner-enrolled keys (SQLite registry; opt-in strict enforcement)
- [x] Persist trusted customer key enrollment, rotation, revocation, and hash-chained audit
- [x] Add fail-closed owner key-control service with verified-principal role checks and actor binding
- [ ] Integrate production identity provider, phishing-resistant MFA, session revocation, and protected API boundary
- [ ] Verify customer acceptance against a trusted contract or payment source
- [ ] Select one narrow service with measurable demand and delivery criteria
- [x] Define isolated execution environments and bounded worker runtimes (initial digest-pinned Docker adapter)
- [x] Add opt-in real-Docker acceptance tests and a manually triggered digest-pinned GitHub Actions workflow
- [ ] Run real-container acceptance against a reviewed worker image
- [ ] Deploy on a hardened runner and pass adversarial isolation tests
- [ ] Connect accepted runtime execution to persisted task lifecycle and artifact evidence
- [ ] Add permitted source adapters and discover real paid work
- [ ] Owner-approved contracts and customer commitments
- [ ] Deliver work and independent quality review
- [ ] Verify settlement and calculate realized net profit/loss
- [ ] Add a capped agent operating budget only after the workflow is proven

## 5 — Autonomous Treasury and Capital Allocation

- [ ] Unified balance sheet
- [ ] Cash-flow forecasting
- [ ] Opportunity scanner and resource allocator
- [ ] Risk-adjusted yield engine
- [ ] DeFi protocol monitoring
- [ ] Portfolio allocation proposals
- [ ] Reproducible out-of-sample evaluation and paper trading
- [ ] Policy-bounded autonomous rebalance after independent review

## 6 — Crypto Testnet and Real Financial Rails

- [ ] Smart-account abstraction
- [ ] Testnet signer
- [ ] Stablecoin transfers
- [ ] Address / contact resolution
- [ ] Transaction simulation
- [ ] Allowance protection
- [ ] Session permissions
- [ ] Emergency revoke / freeze
- [ ] Fiat/payment connectors
- [ ] Broker/fund connectors
- [ ] Strong owner authentication
- [ ] Compliance-aware transaction routing

## 7 — Advanced Security

- [ ] Hardware-backed signing
- [ ] Cryptographic agility
- [ ] Hybrid authorization
- [ ] Post-quantum authorization research
- [ ] Formal verification of critical contracts
- [ ] External security review

## Long-Term Vision

OWNERA should evolve into an owner-directed autonomous treasury and agent operation that can discover opportunities, deliver useful work, acquire permitted resources, earn revenue, manage an operating budget, and seek better risk-adjusted use of capital while protecting the owner's assets and preserving an owner-only Sovereign Reserve.

A list of opportunities, a submitted application, a simulated balance, an invoice, a backtest, or a model's profit forecast is not proof of acquired resources or realized profit.
