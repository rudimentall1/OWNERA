# OWNERA — Regulatory Readiness

> Working architecture document. This is not legal advice and does not establish regulatory status in any jurisdiction.

## External-review perspective

A regulator, bank partner, licensed broker, CASP, EMI, or institutional security reviewer should evaluate OWNERA as a system that may combine AI decisioning, payment initiation, crypto-asset services, investment activity, custody/delegation, and automated execution.

The design therefore follows a **regulated-core / non-custodial-core separation**.

## 1. Current assessment

At the architecture/foundation stage, OWNERA is **not ready to operate as a regulated financial service**. The repository currently defines safety and authorization boundaries, but production integrations, identity controls, compliance controls, operational resilience, and independent assurance are not implemented.

Target posture for 2027–2029:

- no hidden custody by the AI layer;
- explicit jurisdiction and product boundaries;
- auditable authorization and execution;
- deterministic controls around model-driven actions;
- strong customer authentication and recovery;
- transaction monitoring and sanctions/AML controls where applicable;
- documented outsourcing/cloud/model risk;
- incident response and business continuity;
- penetration testing and independent security review;
- cryptographic agility and post-quantum migration planning.

## 2. Regulatory perimeter must be explicit

OWNERA should not claim to be a bank, broker, investment manager, payment institution, or crypto-asset service provider merely because it can connect to those systems.

The implementation must distinguish between:

1. **Owner-controlled software** — interfaces, local signing, policy enforcement, portfolio aggregation, and orchestration.
2. **Licensed third-party services** — banks, payment institutions, brokers, exchanges, CASPs, custodians, and fund providers.
3. **OWNERA regulated capabilities** — capabilities that would only be activated after the required legal entity, permissions, controls, and jurisdictional authorization exist.

Under MiCA, persons providing covered crypto-asset services in the EU generally need the appropriate authorization or another permitted regulatory status. See Regulation (EU) 2023/1114, Article 59.

## 3. Investment autonomy

Investment features must be separated into capability levels:

- market information;
- educational analysis;
- recommendation/proposal;
- owner-confirmed execution;
- policy-bounded autonomous execution.

The product must determine, per jurisdiction and activity, whether a feature constitutes investment advice, portfolio management, order execution, or another regulated activity.

AI confidence must never substitute for required suitability, appropriateness, best-execution, disclosure, recordkeeping, or human-oversight obligations where applicable.

## 4. Payment autonomy

Payment capabilities must support:

- strong customer authentication;
- beneficiary verification;
- transaction and daily limits;
- fraud/anomaly controls;
- idempotency;
- replay protection;
- audit trail;
- dispute/reversal handling where supported;
- clear customer authorization semantics.

Voice is an input method, not proof of authorization by itself.

## 5. Crypto and custody boundary

The preferred architecture is non-custodial wherever practical:

```text
AI / Cloud
  |
  | intent only
  v
Policy + Risk + Firewall
  |
  | authorization request
  v
Owner-controlled signer / licensed execution provider
  |
  v
Blockchain / regulated financial venue
```

The AI service must not receive raw private keys.

## 6. Sovereign Reserve

The Sovereign Reserve is a separate trust domain and a security invariant, not a subscription feature.

Required semantic guarantees:

```text
Agent:       READ        optional
Agent:       DEPOSIT     allowed only by policy
Agent:       WITHDRAW    NEVER
Agent:       TRANSFER    NEVER
Agent:       RECONFIGURE NEVER
```

The implementation must prove that no agent-controlled credential, session key, API credential, upgrade authority, or fallback path can withdraw or reconfigure the reserve.

## 7. AI governance

For every high-impact financial action OWNERA should be able to reconstruct:

```text
user / trigger
  -> intent
  -> agent plan
  -> data sources
  -> model/version
  -> policy version
  -> risk result
  -> authorization decision
  -> signer identity
  -> execution result
```

Model output is treated as untrusted input to authorization.

The system should support model substitution without changing owner authority or financial policy semantics.

## 8. Security assurance target

Before production autonomous execution, OWNERA should plan for:

- threat modeling;
- secure SDLC;
- dependency and supply-chain controls;
- secrets isolation;
- hardware-backed keys where supported;
- penetration testing;
- smart-contract audit where applicable;
- red-team testing of prompt/tool injection;
- incident response exercises;
- recovery testing;
- immutable or tamper-evident audit storage.

## 9. Post-quantum readiness

OWNERA should use crypto-agile interfaces and should not market itself as quantum-safe merely because a post-quantum library is integrated.

The system should support migration planning for NIST standards including ML-DSA and SLH-DSA, while preserving a replaceable authorization interface for future standards. NIST recommends organizations begin migration to post-quantum cryptography now and describes a transition toward quantum-resistant standards.

## 10. External reviewer acceptance criteria

A high-assurance reviewer should be able to answer YES to all of the following before real-money autonomous operation:

- Can the model move money without passing deterministic controls? **No.**
- Can the model obtain raw signing keys? **No.**
- Can an agent credential withdraw from the Sovereign Reserve? **No.**
- Can policy changes happen silently? **No.**
- Can every material action be reconstructed after the fact? **Yes.**
- Can autonomy be revoked quickly? **Yes.**
- Can the system fail closed when a dependency is unavailable or suspicious? **Yes.**
- Can cryptographic providers be migrated without redesigning the treasury model? **Yes.**
- Are regulated functions clearly separated from software-only functions? **Yes.**
- Can a user export/recover their records, policies, and assets without OWNERA becoming a single point of failure? **Yes.**

## 11. Product principle

**Sell autonomy, not custody.**

When a regulated partner is required, OWNERA should integrate with the partner rather than pretending software architecture alone removes the legal requirement.
