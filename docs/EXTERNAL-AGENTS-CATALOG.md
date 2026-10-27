# External Agent and Trading Stack Catalog

Status: research inventory only. Nothing in this document is installed, forked, or authorized to trade live funds.

Last reviewed: 2026-10-27.

## Decision

Do not fork every project into OWNERA and do not merge their source trees into the core repository. Keep OWNERA as the financial control plane. Treat external projects as replaceable, isolated providers that return proposals or operate behind a narrowly scoped execution adapter.

Recommended first stack to evaluate:
1. FinRobot for financial research and structured analysis.
2. TradingAgents for multi-agent decision-workflow experiments.
3. Hummingbot for a potential crypto trading/execution engine, isolated from OWNERA.
4. CCXT as an exchange API library behind an execution adapter, not as an autonomous strategy.
5. Freqtrade as a backtesting/strategy engine candidate, only in a separate process/container pending GPL-3.0 distribution review.

Do not integrate all five at once. First stage all candidates and their licenses, pin versions/commits, then validate one vertical slice at a time.

## Candidate register

| Project | Upstream | Intended role in OWNERA | License signal | Initial decision |
|---|---|---|---|---|
| FinRobot | https://github.com/AI4Finance-Foundation/FinRobot | Financial research, valuation, analysis workflows, structured reports | Apache-2.0 per upstream repository | Evaluate first for research/proposal generation. Do not grant execution authority. |
| TradingAgents | https://github.com/TauricResearch/TradingAgents | Multi-agent market-analysis and decision-workflow experiments | Apache-2.0 per upstream repository | Evaluate as a research benchmark, not a proven profitable trading system. |
| Hummingbot | https://github.com/hummingbot/hummingbot | Strategy runtime, market making, arbitrage and order lifecycle | Apache-2.0 per upstream repository | Strong candidate for a separate execution engine; isolate it and keep OWNERA as final policy gate. |
| CCXT | https://github.com/ccxt/ccxt | Exchange market-data and trading API adapter library | MIT per upstream repository | Preferred connector candidate; never let an agent call private trading methods directly. Wrap allowlisted methods behind OWNERA. |
| Freqtrade | https://github.com/freqtrade/freqtrade | Backtesting, strategy evaluation and optional isolated engine | GPL-3.0 per upstream repository | Useful technical candidate, but do not embed/distribute it with OWNERA until licensing implications are reviewed. |
| Jesse | https://github.com/jesse-ai/jesse | Strategy development, backtesting and optimization | MIT shown for core repository; verify all bundled dependencies and assets | Secondary backtesting candidate. |
| OctoBot | https://github.com/Drakkar-Software/OctoBot | Existing strategy automation and integrations | GPL-3.0 per upstream repository | Lower priority until its architecture, deployment surface and license obligations are reviewed. |

License labels are screening signals, not legal advice. Re-check the exact commit's LICENSE, dependencies, model/data terms, trademarks, and any separate modules before use or redistribution. A permissive top-level license does not automatically cover third-party services, datasets, model weights, or all dependencies.

## Why these projects are not interchangeable

- FinRobot and TradingAgents primarily help research, analyze, or produce candidate decisions. Their output should be treated as untrusted evidence/proposals.
- Hummingbot and Freqtrade are closer to trading engines and can have order-placement capabilities. They must run in a separate process/container with no OWNERA signing keys and no direct path around the OWNERA policy gate.
- CCXT is a connector library, not a strategy or proof of profitability. Its private exchange methods are execution-capable and must be wrapped by a restricted adapter.
- Backtests and agent-generated rationales do not prove live profitability. Require out-of-sample tests, realistic fees/slippage, drawdown, liquidity assumptions, and paper trading before considering live execution.

## Integration contract

Every strategy provider must return a proposal-only payload with:
- provider ID and pinned provider version/commit;
- asset, side, exact decimal quantity, exact decimal price, currency;
- observation timestamp and market-data source identifiers;
- strategy/run ID and rationale;
- optional confidence/metrics, clearly labelled as provider claims.

OWNERA must independently validate the schema, asset allowlist, market snapshot freshness, price/quantity precision, notional, portfolio exposure, liquidity, turnover, daily limits, reserve floor, idempotency, and risk policy. The adapter must reject floats for money/quantity fields and fail closed on unknown fields or stale/missing data.

Execution must remain a separate contract:
1. Provider proposes.
2. OWNERA validates and evaluates risk/policy.
3. Verigate authorizes the exact canonical action.
4. An allowlisted executor receives only the signed, bounded action.
5. External execution is reconciled against exchange/broker receipts.
6. OWNERA stores outcome and evidence; a proposal or authorization alone is not proof of execution or settlement.

## Isolation requirements before running third-party code

- Run each engine as a separate unprivileged OS user/container.
- No Docker socket, host filesystem mounts, SSH keys, cloud credentials, OWNERA database write access, Verigate signing keys, or wallet private keys.
- Network egress allowlist; no inbound public port by default.
- Read-only input snapshot; output only a schema-validated proposal artifact or a narrow local API response.
- Separate credentials for any later executor; withdrawals disabled where the venue supports it.
- CPU, memory, process, and runtime limits; pinned dependencies and image digests.
- Log provider version, configuration hash, market-data provenance, input hash, output hash, and evaluation result.
- Never put live exchange credentials into prompts or pass them to a model.

Containerization reduces risk but does not itself establish a complete security boundary. Review the engine's tools, subprocess behavior, dependencies, and network access before running it.

## Staging plan

### Stage A — inventory (current)
- Keep this register in OWNERA.
- Record upstream URL, exact commit/tag, license, Python/runtime needs, dependency footprint, API shape, security findings, and integration mode.
- Do not fork or vendor code just to keep a list of candidates.

### Stage B — research-only providers
- First connect one research provider through `ValidatedStrategyAdapter`.
- Add a reproducible benchmark with fixed market snapshots and pinned provider versions.
- Compare with OWNERA's deterministic baseline; include fees, slippage, max drawdown, turnover, volatility and out-of-sample periods.
- Keep outputs proposal-only and simulated.

### Stage C — isolated engine
- Evaluate Hummingbot or Freqtrade separately; do not run both live.
- Put all execution behind a narrow adapter that accepts only an OWNERA/Verigate-authorized action.
- Demonstrate that a direct unauthorized order attempt is denied and recorded.

### Stage D — controlled test environment
- Paper trading first, then testnet if the venue supports it.
- Independently reconcile submitted orders, fills, fees, cancellations and balances.
- Do not enable live-money execution until threat model, key isolation, failure recovery, and legal review are complete.

## Forking policy

Default: **do not fork**. Track upstream with pinned release/commit and run it as a separately deployed dependency. Fork only when a concrete required patch cannot be contributed upstream or maintained through an adapter. If a fork is necessary, keep a documented upstream remote, license notices, patch set, update procedure, and a clear reason for diverging.

## Research references

- Hummingbot repository and architecture: https://github.com/hummingbot/hummingbot
- CCXT exchange library and license: https://github.com/ccxt/ccxt
- Freqtrade repository: https://github.com/freqtrade/freqtrade
- Jesse repository: https://github.com/jesse-ai/jesse
- FinRobot repository: https://github.com/AI4Finance-Foundation/FinRobot
- TradingAgents repository: https://github.com/TauricResearch/TradingAgents
- OctoBot repository: https://github.com/Drakkar-Software/OctoBot
