# Open-Duet Integration Boundary

Status: pinned source for evaluation only. It has not been installed, executed, audited, or connected to OWNERA.

## Why this source is tracked

The official [Claude Duet announcement](https://claude.com/resources/articles/claude-duet) does not publish Anthropic's application source code. [Open Duet](https://github.com/Anil-matcha/open-duet) is a separate, community-maintained implementation of an agent workspace with persistent conversations, memory, routines, delegation, and optional isolated computers.

## Source pin

- Repository: https://github.com/Anil-matcha/open-duet
- Upstream commit: `9b67118d9f18de70fbce394093c9c95aeb79045e`
- Observed: 2026-10-28
- Repository license: Apache-2.0; keep its LICENSE and applicable notices with the submodule. Re-check bundled dependencies, connectors, and assets before distributing a combined product.
- Location: `integrations/open-duet` Git submodule, pinned to the commit above.

Fetch the source explicitly when needed:

```bash
git submodule update --init --recursive integrations/open-duet
```

The root checkout contains a pinned submodule reference, not a copied or modified source tree. To update it, review the upstream diff and license first, then change the gitlink SHA in a reviewed commit.

## OWNERA trust boundary

Open Duet is an untrusted agent/task orchestration layer. Its approval prompt is not financial authorization. It must never be given:

- wallet private keys, signer credentials, exchange withdrawal keys, or Verigate signing material;
- write access to OWNERA's ledger, policy database, audit evidence, or Sovereign Reserve;
- an unrestricted wallet/payment tool, Docker socket, host filesystem, or broad network egress.

Any future adapter must expose only bounded, schema-validated proposals or read-only results. OWNERA must independently validate intent, risk, authority, limits, destination, replay/idempotency, and reserve invariants. A payment or transfer remains impossible unless OWNERA's deterministic policy and execution path separately allow the exact action. An Open-Duet approval must never bypass those checks.

## Next validation gate

Before running this code, separately review its install/build scripts, dependencies, credential storage, auth/session boundaries, routine/webhook triggers, browser/computer tools, connector scopes, subprocess behavior, network egress, and sandbox escape surface. Run it as an unprivileged isolated service with synthetic data and no OWNERA secrets. Verify denial cases and audit continuity before designing any narrow adapter.

No production integration, live-money capability, or security guarantee is claimed by adding this source pin.
