# Resource Autonomy

Status: strategic architecture proposal. This document defines the direction; it does not claim that autonomous resource acquisition or profit generation is implemented.

## Related market research

See [Resource Intelligence Market Research](RESOURCE-INTELLIGENCE-MARKET-RESEARCH.md) for the competitor map, source landscape, jurisdiction analysis, opportunity hypotheses, MVP proposal, risks, and validation backlog. This is research, not implemented functionality.

## Purpose

OWNERA is intended to become an owner-directed autonomous treasury and agent operating system. In addition to protecting and managing assets already provided by the owner, it should help discover, earn, obtain, allocate, and account for resources needed to carry out the owner's goals.

The long-term objective is an owner-controlled agent operation: a coordinated group of specialized agents that can discover useful work and opportunities, deliver services, earn revenue, acquire permitted infrastructure, manage an operating budget, and report realized results to the owner.

This is not a promise of passive income or guaranteed profit. Agents can lose money, fail to find customers, misjudge opportunities, or incur costs. OWNERA must measure outcomes and preserve owner control.

## Product distinction

OWNERA must distinguish three pools:

1. **Owner assets** — assets belonging to the owner and governed by the Owner Constitution.
2. **Agent operating budget** — a specifically allocated, capped budget for approved operating costs.
3. **Sovereign Reserve** — an owner-controlled protected reserve that agents cannot withdraw, transfer, pledge, or reconfigure.

Revenue earned by an agent is not automatically its unrestricted property. The Owner Constitution and explicit allocation policy determine how receipts are split between operating costs, taxes/fees, reserve contributions, owner distributions, and any permitted reinvestment.

An agent must never silently convert a resource-discovery task into authority to borrow, pledge collateral, sell owner assets, spend reserve funds, or accept an obligation.

## Resource classes

The Resource Autonomy Engine should search beyond cash. Every opportunity must be classified by resource type, owner, legal basis, cost, restrictions, expiry, and required permission.

- **Capital:** grants, bounties, paid contracts, sponsorships, investment offers, revenue-sharing agreements, and loans that have been explicitly approved.
- **Compute:** cloud credits, GPU capacity, sponsored infrastructure, rented capacity, and authorized idle capacity.
- **Infrastructure:** hosting, domains, storage, APIs, software credits, deployment services, and monitoring.
- **Work and revenue:** paid software tasks, audits, research, automation, support, data processing, and agent-to-agent services.
- **Data and knowledge:** public datasets, open research, licensed data, documentation, and permitted APIs.
- **People and partnerships:** customers, contractors, service providers, mentors, investors, and other agent operators.
- **Distribution:** marketplaces, app directories, partner channels, grants ecosystems, and customer acquisition opportunities.
- **Physical-world resources:** equipment, facilities, logistics, and other resources only through an authorized provider or explicit agreement.

### Dormant and unclaimed assets

Inactivity is not abandonment. An unused bank account, wallet, DAO treasury, cloud account, domain, server, or corporate budget remains controlled by its lawful owner unless a valid legal process establishes otherwise.

OWNERA may discover such assets and identify lawful recovery, claims, licensing, purchase, rental, donation, or partnership routes. It must not attempt unauthorized access, key discovery, credential reuse, exploitation, transfer, or appropriation.

For owner-specific unclaimed property, the agent may help the verified rightful claimant prepare and submit a claim with the claimant's authorization. Public blockchain visibility is not permission to control an address.

## Resource Autonomy Engine (RAE)

RAE is the opportunity discovery and resource acquisition subsystem. It is not a signer and does not grant financial authority.

### Core modules

1. **Resource Scanner** — searches approved public sources, connected accounts, marketplaces, grant directories, service marketplaces, cloud-credit programs, and partner networks.
2. **Opportunity Normalizer** — converts findings into a common structured record with source, timestamp, owner, terms, eligibility, cost, expiry, and evidence.
3. **Eligibility and Rights Checker** — checks whether OWNERA or the owner is eligible and identifies the lawful route to access or use the resource.
4. **Opportunity Analyzer** — estimates expected value, time-to-cash or time-to-capacity, effort, costs, probability, downside, and uncertainty.
5. **Proposal Planner** — prepares a concrete plan, required inputs, deliverables, budget, and acceptance criteria.
6. **Negotiation and Application Agent** — drafts applications, quotes, proposals, and messages. External commitments require the approval level set by policy.
7. **Work Delivery Agents** — perform bounded tasks using approved tools, isolated workspaces, and scoped credentials.
8. **Revenue and Receipt Verifier** — verifies that a promised resource or payment was actually received; a proposal, invoice, or transaction submission is not proof of settlement.
9. **Resource Allocator** — allocates received resources to approved projects and budgets.
10. **Performance Ledger** — records costs, hours, revenue, realized profit/loss, resource utilization, refunds, disputes, and evidence.

## Agent farm

The agent farm is a set of specialized workers coordinated by a planner. Agents are replaceable and untrusted by default.

Initial roles:

- **Coordinator:** breaks owner goals into tasks, assigns work, tracks dependencies, and reports progress.
- **Opportunity Researcher:** finds grants, bounties, paid work, customers, and resource programs.
- **Commercial Agent:** prepares service offers, proposals, quotes, and customer follow-up.
- **Delivery Agents:** execute approved work such as software development, audits, research, content operations, and automation.
- **Infrastructure Agent:** finds and manages approved hosting, compute, API, and software resources.
- **Finance Analyst:** models cash flow, budgets, unit economics, and investment proposals.
- **Investment Researcher:** researches markets and produces evidence-backed investment proposals.
- **Independent Reviewer:** checks deliverables, claims, security, and evidence before submission or release.

No worker receives unrestricted owner credentials or direct access to signing keys. A worker may propose an action; OWNERA independently validates it.

## End-to-end operating cycle

1. Owner defines an objective, deadline, acceptable risk, and permitted resource envelope.
2. Coordinator creates a plan and bounded tasks.
3. RAE discovers opportunities and records evidence and terms.
4. Analyzer ranks opportunities by expected net value, feasibility, time, uncertainty, and downside.
5. OWNERA checks eligibility, authority, budget, and policy.
6. Required approvals are obtained before external commitments, spending, borrowing, or handling sensitive data.
7. Delivery agents perform the work in isolated environments.
8. Independent review checks the deliverable against acceptance criteria.
9. The customer, marketplace, provider, or chain confirms delivery and settlement.
10. OWNERA reconciles receipts, costs, fees, taxes/obligations, and realized profit or loss.
11. Allocation policy distributes funds between owner distribution, approved operating budget, reserve contribution, and explicitly permitted reinvestment.
12. The system updates its performance record and plans the next cycle.

## Financial authority and hard boundaries

The reasoning model, external agent framework, strategy engine, and resource scanner are not financial authorities.

All money movement and binding commitments must pass through OWNERA's deterministic policy and authorization path. Where configured, Verigate can provide an independent authorization and evidence layer for the exact canonical action.

Mandatory controls:

- Separate owner assets, operating budget, and Sovereign Reserve.
- No agent withdrawal, transfer, pledge, or policy modification authority over the Sovereign Reserve.
- No borrowing, leverage, collateralization, guarantees, or recurring obligations without explicit policy permission and required owner approval.
- No use of discovered credentials, private keys, abandoned accounts, or third-party assets without valid authorization.
- Allowlisted counterparties, destinations, services, tools, and data scopes.
- Per-task, per-agent, daily, and aggregate budgets.
- Spending, exposure, loss, and time limits.
- Idempotency, replay protection, transaction simulation where applicable, and independent settlement reconciliation.
- Kill switch, credential revocation, provider isolation, and append-only audit evidence.
- Fail closed when ownership, eligibility, source quality, terms, or authorization are unclear.

The agent may autonomously search and prepare proposals. Whether it may submit an application, accept a contract, purchase a service, execute a trade, or commit to recurring costs is a separate policy decision for each action class.

## Profit and investment policy

The system must optimize for verified net outcomes, not model confidence, gross revenue, token incentives, or backtest returns.

Track at minimum:

- gross receipts and realized revenue;
- direct costs, infrastructure, API, compute, and contractor costs;
- fees, refunds, chargebacks, taxes and other obligations where applicable;
- realized net profit/loss and cash conversion time;
- utilization and cost per completed deliverable;
- customer acquisition and repeat revenue;
- investment return after fees, drawdown, liquidity, and risk;
- forecast versus actual performance.

Investment agents produce proposals only. Live investment authority is a later capability and remains bounded by explicit allocation, asset, exposure, loss, liquidity, and approval policies. No strategy or agent is assumed profitable without reproducible out-of-sample evidence and controlled paper-trading results.

## Security model for external agents and tools

Third-party agent frameworks and task runners are untrusted execution providers. They must be reviewed and isolated before use.

- Dedicated unprivileged process/container or remote worker.
- No host Docker socket, broad filesystem mounts, SSH keys, wallet keys, exchange withdrawal keys, or OWNERA signing material.
- Explicit network egress allowlist and scoped API credentials.
- Bounded input snapshots and schema-validated output.
- CPU, memory, runtime, process, and output-size limits.
- Pinned versions, dependency/license review, reproducible build records, and security review.
- Independent OWNERA validation of all proposals and actions.
- Evidence linking task, agent/provider version, input, output, approvals, execution, and settlement.

Containerization alone is not a complete security boundary. High-risk providers require a separate threat review before execution.

## Phased implementation

### Phase A — Resource discovery in read-only mode

- Define resource opportunity schema and source provenance.
- Add a small set of public, reputable opportunity sources.
- Discover grants, bounties, paid tasks, cloud credits, and open compute programs.
- Deduplicate, score, expire, and track opportunities.
- Produce a daily/weekly opportunity report.
- No external applications, spending, commitments, or financial execution.

### Phase B — Owner-approved acquisition

- Add eligibility checks and application/proposal drafting.
- Require owner approval before submission or commitment.
- Track application status and evidence.
- Add cloud-credit and infrastructure acquisition workflows.
- Verify actual receipt and terms before marking resources as acquired.

### Phase C — Earned revenue

- Select one service the agent farm can reliably deliver.
- Define a narrow service catalog, price, acceptance criteria, and delivery limits.
- Find real customers or paid tasks.
- Require approval for contracts and customer commitments.
- Deliver, independently review, invoice, reconcile payment, and calculate net profit.
- Start with human approval at each external commitment.

### Phase D — Bounded operating autonomy

- Introduce a capped agent operating budget.
- Allow only low-risk, reversible, allowlisted operating expenses within strict limits.
- Add per-agent budgets, anomaly detection, emergency stop, and reconciliation.
- Keep owner distributions and reserve protections independent.

### Phase E — Multi-agent business operations

- Expand specialized delivery agents only when one service has repeatable unit economics.
- Add customer support, sales operations, research, infrastructure, and quality assurance.
- Measure profitability per service and per agent.
- Scale only when verified results justify the added complexity and cost.

### Phase F — Capital allocation and investment

- Add portfolio and investment research as separate proposal-producing capabilities.
- Require backtesting, out-of-sample evaluation, paper trading, and independent risk checks.
- Introduce limited execution only after key isolation, authorization, recovery, and legal reviews.
- Never use the Sovereign Reserve as agent collateral or trading capital.

## First vertical slice

The first proof should not be a large swarm or live trading.

Build one complete, inspectable loop:

1. Discover a real grant, bounty, paid task, or cloud-credit opportunity from a public source.
2. Preserve the source, eligibility rules, deadline, and terms.
3. Evaluate whether OWNERA's current capabilities can satisfy it.
4. Produce a concrete application or delivery plan with budget and expected net value.
5. Obtain owner approval.
6. Submit or perform the work through a bounded workflow.
7. Verify the result and any resource/payment actually received.
8. Record costs, outcome, and evidence.

Success means a real opportunity was discovered and a verifiable resource was acquired or revenue was received. A generated list, simulated balance, submitted application, or uncollected invoice does not count as revenue.

## Non-goals

- Unauthorized access to dormant accounts, wallets, servers, cloud accounts, or third-party resources.
- Treating inactivity, lost keys, public visibility, or weak security as consent.
- Unrestricted autonomous borrowing, leverage, trading, or spending.
- Claiming guaranteed passive income or guaranteed investment returns.
- Scaling the number of agents before proving a profitable, repeatable service.
- Giving external agent frameworks direct access to owner assets or financial authority.

## Relationship to existing OWNERA components

- **Owner Constitution:** defines goals, beneficiary, risk tolerance, and non-negotiable limits.
- **Agent / Coordinator:** plans work and delegates bounded tasks.
- **Policy and Risk Engines:** evaluate opportunity, commitment, spending, investment, and execution proposals.
- **Treasury:** accounts for owner assets, liabilities, cash flow, budgets, and operating resources.
- **Sovereign Reserve:** remains outside agent withdrawal authority.
- **External providers:** perform research or delivery but remain untrusted.
- **Verigate / Transaction Firewall:** independently authorizes exact high-impact actions where integrated.
- **Audit:** preserves opportunity provenance, task evidence, approvals, receipts, and outcomes.
- **Recovery:** stops operations and revokes capabilities after an incident.

The core rule remains: agents may find opportunities and create value, but OWNERA decides what resources they are allowed to acquire, spend, invest, or commit.
