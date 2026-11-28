# Architecture Quality Audit

**Status:** advisory pilot enabled on the `main` branch and pull requests targeting `main`.  
**Workflow:** `.github/workflows/architecture-audit.yml`  
**Scope:** Python source code.

## Purpose

The pilot uses [deslop-please](https://github.com/Bor4brn/deslop-please) to identify structural problems that conventional tests and formatters do not measure directly. Its design principle is deep modules with narrow interfaces.

The scan reports:

- `module-cycle` — cycles between modules;
- `tangle` — tangled dependencies between types, functions, and constants;
- `field-leak` — object fields exposed beyond the object boundary;
- `shallow-module` — modules with an overly broad, shallow interface;
- `wide-directory` — directories with too many source files;
- `long-file` — source files exceeding the configured line threshold.

These findings are architecture signals. Review them in context; do not mechanically move code or change a stable public interface just to reduce a count.

## Pinned toolchain

The workflow pins:

- `deslop-please` to upstream multi-language port commit `cfabfb9ee417e150d5342e8ef0d6a0fe725cc9a0`;
- Rust toolchain `1.99.0` to build the CLI;
- `@sourcegraph/scip-python` `0.6.8` to index Python.

These are CI-only tools. They are not added to OWNERA's runtime or Python development dependencies.

## Execution and reporting

The workflow runs on pushes to `main`, pull requests targeting `main`, and manual dispatch.

The report and indexer stderr are uploaded as the `deslop-please-ownera-<run-id>` artifact for 14 days. The report is JSON.

The CLI uses these exit codes:

- `0`: no architectural findings;
- `1`: architectural findings were reported;
- `2`: the scan could not complete because of a tool, indexer, or configuration error.

The scan step is explicitly advisory: neither findings nor scan-time errors block the existing OWNERA test/lint workflow. A failed installation/setup step still fails the Architecture Audit workflow. The step summary distinguishes findings from an execution failure; an execution failure must never be treated as a clean scan.

No allowlist is configured, and the workflow never runs `--update-allow`. Existing findings remain visible for review instead of being silently baselined.

## Local execution

On an Ubuntu 24.04 environment with Rust 1.99.0 and Node.js 22:

```bash
cargo install --git https://github.com/Bor4brn/deslop-please --rev cfabfb9ee417e150d5342e8ef0d6a0fe725cc9a0 --locked deslop-please
npm install --global --no-audit --no-fund @sourcegraph/scip-python@0.6.8
deslop-please --language python --json
```

The Python SCIP index is cached outside the repository under the user's cache directory. The tool does not rewrite OWNERA source files.

## Limitations

- This pilot checks Python only. If another supported language becomes part of OWNERA, update the workflow and indexer setup intentionally before claiming that language is covered.
- SCIP indexing can resolve fewer references in untyped or dynamically typed code; absence of a finding is not proof that a dependency or encapsulation problem does not exist.
- The tool does not audit financial logic, authorization, cryptography, dependency vulnerabilities, secrets, or runtime isolation.
- It does not replace Ruff, pytest, integration acceptance, threat-model review, or human code review.

## Initial baseline — 2026-11-28

The first completed scan ran as [Architecture Audit run 46112270051](https://github.com/rudimentall1/OWNERA/actions/runs/46112270051) against source head `c3efc4ad967ee62d3a0943cd9c3d9380e9a6829d`.

The analyzer completed with exit code `1` and reported **8 diagnostics**:

| Lint | Count | Initial locations |
|---|---:|---|
| `field-leak` | 6 | `authority_contract.py`, `persistent_commercial.py`, `sandbox.py`, `treasury_cycle.py`, `persistent_workforce.py` / `worker_performance.py` |
| `wide-directory` | 2 | `ownera/`, `tests/` |

The six field diagnostics concern `AuthorityArtifact.decision`, repository event-store access in the commercial/workforce facades, sandbox firewall audit/ledger access, and the investment sandbox portfolio read. These are review targets, not confirmed defects. The two directory-size findings are structural warnings, not a reason to split files mechanically.

The normal OWNERA CI run `46112270513` passed for the same branch head. The architecture result is separate from application tests. No source code was changed to address this baseline; no diagnostic was suppressed. Keep this section as a dated snapshot, not as a claim about later commits.
