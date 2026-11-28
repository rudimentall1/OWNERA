# OWNERA — Agent Instructions

## Project boundaries

- Read `README.md`, `docs/ARCHITECTURE.md`, and the relevant domain/security documents before changing a subsystem.
- Preserve the separation between agent reasoning, deterministic policy authorization, and execution.
- Never weaken owner authority, sovereign-reserve protections, spending limits, evidence integrity, or fail-closed behavior to make a test pass.
- Prefer existing module boundaries and dependency conventions. Do not add runtime dependencies for development-only checks.
- Keep documentation synchronized with significant architecture, configuration, workflow, and behavior changes.

## Verification

- Use the commands documented by `pyproject.toml` and the repository CI: `ruff check .` and `pytest -q`.
- Do not claim a test, integration, or live execution passed unless it was actually run and its result inspected.
- Keep real-Docker acceptance tests separate from the default unit suite; they require the explicit integration workflow and a digest-pinned image.

## Architecture quality review

- The advisory architecture scan is defined in `.github/workflows/architecture-audit.yml` and documented in `docs/ARCHITECTURE-QUALITY.md`.
- The pilot scans Python with the pinned `deslop-please` tool and `scip-python` indexer.
- Treat findings as evidence to investigate, not as instructions to mechanically move code or change public APIs.
- Fix confirmed structural problems at their source. Do not suppress findings with an allowlist or `--update-allow` unless the baseline is reviewed and the exception is documented.
- This scan is not a security audit and does not replace tests, Ruff, dependency review, or threat-model review.
