# Immunefi Research Triage: Charm Alpha Vaults V2

**Review date:** 2026-11-01
**OWNERA status:** Candidate selected for local-only validation. No vulnerability has been confirmed and no report has been submitted.

## Why this candidate

The public Immunefi program currently lists three in-scope assets and was last updated on 2026-09-02. Its information page lists fixed smart-contract rewards of USD 1,000 Low, USD 1,500 Medium, USD 3,000 High, and USD 6,000 Critical. Payout is in ETH or USDC. KYC is not required. A PoC is required for every severity.

Official pages:

- Program information: https://immunefi.com/bug-bounty/charm/information/
- Program scope: https://immunefi.com/bug-bounty/charm/scope/
- Program resources: https://immunefi.com/bug-bounty/charm/resources/
- Immunefi-wide rules: https://immunefi.com/rules/

Program restrictions include no testing against mainnet or public-testnet deployed code, no testing with pricing oracles or third-party smart contracts, no denial-of-service testing, and no high-traffic automated testing. The permitted PoC path is a local fork or controlled local environment. Immunefi-wide rules prohibit testing live mainnet/public-testnet contracts and low-quality or incomplete submissions.

## Source provenance

Official source repository: https://github.com/charmfinance/alpha-vaults-v2-contracts
Reviewed source revision: `0174095f918b5a883c3726cbe4556aaa58f12c82`
Revision date: 2023-06-26
Compiler pragma: Solidity `^0.7.6`
Key dependencies: OpenZeppelin Upgradeable 3.4.0, Uniswap V3 core/periphery 1.0.0.

The catalog's three asset references are:

- `contracts/AlphaProVault.sol`
- `contracts/AlphaProVaultFactory.sol`
- `contracts/CloneFactory.sol`

The repository also contains `AlphaProPeriphery.sol` and `ManagerStore.sol`; do not assume these are covered by the current three-asset program scope.

## Prior known change to avoid duplicating

The latest repository commit is titled `fix vault shares leftover vulnerability. fix manager deauth`. It added `MINIMUM_LIQUIDITY = 1e3`, permanently minted the initial minimum shares to the factory, and changed first-deposit share calculation to subtract that minimum. This is a known, patched issue in the public history and must not be submitted as a new finding.

## Initial attack-surface map

- Vault accounting: first deposit, proportional deposits, share mint/burn, residual minimum liquidity, fee collection, and total-amount views.
- Uniswap V3 positions: full-range, base, and limit ranges; `burn`, `collect`, `mint`, tick alignment, TWAP checks, and fee accrual.
- Callbacks: `uniswapV3MintCallback` and `uniswapV3SwapCallback` require `msg.sender == pool`.
- Manager authority: manager transfer, rebalance delegate, fee changes, emergency burn, and fee collection.
- Factory: permissionless `createVault`, clone creation, vault registry, governance, and protocol fee cap.

## Unconfirmed hypothesis for falsification

`AlphaProVaultFactory.createVault` accepts `VaultParams.pool` without an explicit canonical Uniswap V3 factory/pool provenance check. `AlphaProVault.initialize` stores that address, and the callback functions trust the stored pool address as the caller. Investigate whether a malicious pool address can be used to create a factory-registered vault that can transfer deposited token balances through its callback interface.

This is **not a confirmed vulnerability**. A critical eligibility question is whether any resulting loss would be considered a contract flaw in the in-scope assets or merely a user choosing an attacker-created, non-canonical vault. The factory appears permissionless, so the realistic user-discovery and trust assumptions must be established before claiming impact. If the issue requires social engineering or a user knowingly depositing into an obviously malicious vault, it may be rejected or out of scope.

Validation must be confined to a local test harness. Do not call live contracts, create public-testnet deployments, interact with real users, or use third-party systems. If a local proof does not establish a meaningful in-scope impact without social engineering, close the hypothesis and move on.

## Current disposition

`NEEDS_LOCAL_VALIDATION`. No target interaction, scanning, transaction, or report submission has occurred. Do not infer expected income from the USD 6,000 maximum program reward.

## Local-only hypothesis test and disposition

A disposable Hardhat harness (not committed to the Charm repository) confirmed that an attacker-controlled pool contract can call the vault's callback and receive the deposited ERC-20 balances of a vault configured with that pool address. The local test passed. This demonstrates the callback trust assumption, but it does **not** establish an eligible bounty finding by itself.

The official Charm user documentation states that the default Alpha Vaults home page displays vaults created by verified managers; unverified-manager vaults are hidden unless a user knows the manager address. See https://learn.charm.fi/charm/provide-liquidity/user-guides/home-page. This materially weakens the realistic victim path: the test requires a depositor to select an attacker-created vault whose manager is not verified. No independent path to cause deposits into that vault was established.

**Disposition: CLOSED_NOT_REPORTABLE on current evidence.** Do not submit this as a finding. Do not attempt social engineering or live testing to manufacture impact. Retain the test as a negative validation artifact only. Continue with other code-level hypotheses that can demonstrate an in-scope impact without relying on user deception.
