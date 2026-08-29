# OWNERA Financial Safety Invariants

These invariants are intended to become executable tests and, where applicable, formal specifications before real-money autonomy.

## I1 — Agent is never the sole authority

No model output, prompt, tool result, or agent session may by itself authorize protected financial execution.

## I2 — Sovereign Reserve is monotonic for the agent

From the agent trust domain:

```text
reserve_balance(t+1) >= reserve_balance(t)
```

An agent-controlled path may contribute to the reserve only. Withdrawal, transfer, and reconfiguration authority must remain outside that domain.

## I3 — Paid plans never weaken security

Subscription entitlements may add product capabilities but can never bypass policy, risk, authentication, recovery, or reserve invariants.

## I4 — Fail closed

Material uncertainty, missing verification, stale critical data, unavailable policy/risk services, connector inconsistency, or signer ambiguity must never silently become ALLOW.

## I5 — No silent privilege escalation

The agent cannot increase its own spending limits, add itself as an authorized signer, disable monitoring, alter constitutional rules, or create equivalent authority through another tool.

## I6 — Explicit intent

Every financial execution must resolve to a structured intent containing enough information to identify what is being executed, for whom, for what amount, and under which authority.

## I7 — Replay resistance

Executable intents require an idempotency/replay-control mechanism appropriate to the external rail.

## I8 — Audit continuity

A material authorization decision produces an attributable audit event before and after execution, with enough references to reconstruct the decision path.

## I9 — Recovery independence

Owner recovery must not require the agent's memory, model availability, cloud service, or cooperation.

## I10 — Cryptographic agility

Authorization must be abstracted from a single signature algorithm so that a future migration can occur without changing owner policy semantics.

## Verification status

These are design invariants. They are not yet claims of formal verification or production compliance. Each invariant must eventually have executable tests; critical wallet/contract invariants should additionally be formally specified and independently reviewed before production autonomy.
