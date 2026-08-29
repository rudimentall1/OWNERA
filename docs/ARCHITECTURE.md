# OWNERA Architecture

## 1. System Boundary

OWNERA is an autonomous personal treasury. It sits between the owner's intent and external financial systems.

The architecture must keep three concerns separate:

- **Reasoning** — what the agent believes should happen.
- **Authorization** — whether the requested action is allowed.
- **Execution** — how an approved action is signed and submitted.

A model failure must not automatically become a financial authorization failure.

## 2. Trust Domains

### Owner domain

The strongest trust domain. Contains owner identity, recovery material, constitutional rules, and the Sovereign Reserve authority.

### Agent domain

Contains models, memory, planning, tool usage, market research, and task execution. It is intentionally less trusted than the owner domain.

### Policy domain

Deterministic authorization layer. Evaluates intents against explicit rules, limits, destinations, assets, time windows, risk thresholds, and required approvals.

### Execution domain

Contains signers, smart accounts, bank/payment connectors, and blockchain RPC interfaces.

### External domain

Untrusted by default: websites, APIs, protocols, counterparties, contracts, market data, and third-party tools.

## 3. Canonical Action Flow

```text
Owner request / Autonomous trigger
                |
                v
        Intent extraction
                |
                v
         Agent planning
                |
                v
       Tool/data acquisition
                |
                v
        Risk evaluation
                |
                v
       Policy evaluation
                |
                v
      Execution preparation
                |
                v
     Transaction simulation
                |
                v
      Deterministic gate
          /          \
       DENY          ALLOW
        |               |
      record         signer
                        |
                        v
                    execution
                        |
                        v
                    verification
                        |
                        v
                     audit
```

## 4. Owner Constitution

The constitutional layer expresses the owner's durable objectives and safety principles. It is not treated as an arbitrary natural-language instruction that can be silently rewritten by the agent.

Conceptually:

```text
Owner Constitution
        +
Structured Policies
        +
Security Invariants
        ↓
Effective Authority
```

Changes to constitutional controls should require owner authorization and be strongly authenticated.

## 5. Policy Engine

The Policy Engine is deterministic wherever practical.

Example policy dimensions:

- maximum transaction amount
- daily / weekly budget
- asset allowlist
- destination allowlist
- contract allowlist / denylist
- permitted protocols
- minimum liquidity
- maximum slippage
- maximum portfolio concentration
- minimum cash reserve
- required approval level
- geographic / provider restrictions
- emergency mode

The policy result should be machine-readable:

```json
{
  "decision": "ALLOW | DENY | REVIEW",
  "reason_codes": [],
  "policy_version": "...",
  "required_approvals": 0
}
```

## 6. Risk Engine

The Risk Engine evaluates contextual risk independently of the model's confidence.

Initial risk categories:

- counterparty risk
- transaction risk
- smart-contract risk
- liquidity risk
- market / volatility risk
- oracle / data quality risk
- protocol risk
- operational risk
- key / identity risk
- anomaly risk

The system should preserve raw evidence used for important decisions.

## 7. Sovereign Reserve

The Sovereign Reserve is intentionally outside normal agent authority.

Desired invariant:

```text
Agent capabilities:
    READ        optional
    DEPOSIT     optional / allowed by policy
    WITHDRAW    NEVER
    TRANSFER    NEVER
    RECONFIGURE NEVER
```

For an on-chain implementation, reserve withdrawal authority must not be derivable from an agent-controlled key, role, session key, or tool.

The reserve is treated as a separate trust domain rather than merely another wallet balance.

## 8. Wallet and Authorization Abstraction

Wallet support should be provider-agnostic.

```text
SignerProvider
├── Local / development signer
├── Hardware-backed signer
├── Smart-account authorization
├── Multisig authorization
└── Future hybrid / post-quantum provider
```

The application should never require the AI model to possess raw private key material.

## 9. Autonomous Treasury

The Treasury layer maintains the owner's financial state:

```text
Assets
Liabilities
Cashflow
Budgets
Positions
Obligations
Goals
Risk limits
```

It provides a normalized view across fiat, crypto, DeFi, and future investment connectors.

## 10. Investment and DeFi Engine

Investment decisions should be represented as explicit proposals before execution.

Example:

```json
{
  "objective": "increase risk-adjusted return",
  "capital": "2000 EUR",
  "horizon_days": 365,
  "max_loss": 0.10,
  "liquidity_requirement_days": 7,
  "proposal": {}
}
```

The engine should distinguish:

- expected yield
- realized yield
- fees
- liquidity constraints
- volatility
- smart-contract risk
- counterparty risk
- concentration

Yield alone must never determine allocation.

## 11. Voice Interface

Voice is an input channel, not an authorization mechanism by itself.

A spoken command such as "send 300 to Alex" must become a structured intent and then pass through identity, ambiguity resolution, policy, and risk controls.

## 12. Auditability

Important actions should generate append-only events.

```text
intent.created
plan.created
risk.evaluated
policy.evaluated
execution.approved
transaction.submitted
transaction.confirmed
portfolio.changed
reserve.contribution
emergency.triggered
```

Each event should carry timestamps, actor, correlation ID, policy version, and relevant hashes / references.

## 13. Emergency Controls

The architecture should support an owner-triggered emergency mode that can:

- stop new autonomous execution
- revoke active sessions
- freeze supported smart-account spending
- block selected connectors
- preserve audit data
- require explicit recovery before autonomy resumes

## 14. Post-Quantum Readiness

Quantum-safe support is designed as a pluggable authorization capability, not a hard-coded wallet type.

The target is cryptographic agility:

```text
AuthorizationScheme
├── Classical
├── Hybrid
└── PostQuantum
```

The implementation must not claim quantum resistance merely because a PQ algorithm library is present; the complete authorization and recovery path must be evaluated.

## 15. Development Rule

No production-money integration should bypass the policy, risk, audit, and authorization layers for convenience.

The architecture should make the safe path the easiest path.
