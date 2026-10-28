# Open Duet security review

Status: preliminary static review, not a security audit or runtime qualification.

Reviewed source: `Anil-matcha/open-duet` at pinned commit `9b67118d9f18de70fbce394093c9c95aeb79045e` (submodule `integrations/open-duet`). This document records risks relevant to using Open Duet alongside OWNERA. No Open Duet code was changed by this review. The source and its test files were read through GitHub; tests were not executed in this review.

## Decision

Keep the dependency classified as `pinned-source-unreviewed`. Do not run it with OWNERA secrets, signing material, financial-policy write access, wallet credentials, or production payment tools. A pinned source tree is not an integrated or trusted component.

## Findings

### OD-01 — Generic ACP commands can execute without the optional host sandbox

**Risk: High for any deployment that gives an ACP agent access to valuable host data or credentials.**

Evidence:
- `backend/app/services/acp_adapter.py`: the generic ACP adapter accepts a configured executable/command and starts one process per turn. Its permission handler gates `session/request_permission` requests, but the adapter's own module documentation explicitly notes that what an agent does without asking is up to the agent.
- `backend/app/core/turn_sandbox.py`: when `TURN_SANDBOX_ENABLED` is false, `self_check()` returns status `off` and `command()` returns the original arguments unchanged.
- `backend/app/core/config.py`: `TURN_SANDBOX_ENABLED` defaults to `False`; network isolation also defaults to `False`.
- `backend/tests/core/test_turn_sandbox.py`: tests explicitly assert that the disabled sandbox preserves the original command unchanged.

Impact:
The approval gate only governs permission requests the external ACP process chooses to send. It is not an operating-system boundary against a malicious or non-conforming configured executable. With the sandbox disabled, such a process can run with the service account's normal OS permissions.

Required before any OWNERA adapter:
1. Run Open Duet under a separate unprivileged OS account or disposable VM/container, with no OWNERA files, wallet profiles, signer material, Docker socket, or shared credential directories mounted.
2. Use default-deny network egress outside the process; do not treat the optional HTTP(S) gate as active unless its Linux namespace configuration is explicitly enabled and verified.
3. For a future integration, accept only bounded proposals and read-only results. OWNERA must independently authorize every financial action.
4. Add an adversarial ACP fixture that executes a side effect without sending `session/request_permission`; demonstrate that the isolation boundary blocks it. If isolation is unavailable, fail closed rather than launch the configured agent.

### OD-02 — Connected-app credential exposure to local agent commands is documented

**Risk: High when connected apps and local command tools are enabled together.**

Evidence: `docs/CONNECTED_APPS.md` at the pinned commit states that the saved Composio project key is encrypted at rest but, until a credential broker exists, is visible to the local user's agent shell commands.

Impact:
An agent or command it runs may be able to read or exfiltrate that credential. Encryption at rest does not protect a secret from a process that can access it at runtime.

Required mitigation:
- Do not connect OWNERA-sensitive accounts or enable local shell tools in the same trust domain.
- Do not pass OWNERA API keys, exchange withdrawal keys, wallet/signer credentials, or Verigate signing material into Open Duet.
- Before using connected apps in a sensitive deployment, implement and test a credential broker that keeps provider secrets out of agent and shell environments.

### OD-03 — Network isolation is opt-in, not a default property

**Risk: High if an operator assumes the optional gate is always active; otherwise an explicit deployment limitation.**

Evidence:
- `backend/app/core/config.py` defaults both `TURN_SANDBOX_ENABLED` and `TURN_SANDBOX_NETWORK_ENABLED` to false.
- `backend/app/core/turn_sandbox.py` reports `network: unrestricted` when the sandbox is off or when only filesystem/PID isolation is enabled.
- `backend/tests/core/test_turn_egress.py` includes policy and transport tests, plus a real Linux test guarded by platform and bubblewrap availability.

Impact:
A deployment using default settings does not gain network restrictions from `turn_egress.py`. Unit-test presence does not establish that a deployed Linux kernel, bubblewrap installation, and provider process are isolated.

Required mitigation:
- Apply independent network egress controls at the VM/container/firewall layer.
- If enabling the optional Linux network gate, run the real Linux qualification tests on the target deployment and verify that private/loopback destinations are blocked and public HTTP(S) works only through the gate.
- Record the effective configuration and test result as deployment evidence.

### OD-04 — Engine login profiles remain part of the agent's trust boundary

**Risk: High if host account profiles are shared with OWNERA or other valuable services.**

Evidence: `backend/app/core/turn_sandbox.py` intentionally grants the selected engine's login directory (for example `.claude` or `.codex`) as a writable mount when sandboxing is enabled. The sandbox implementation is designed to keep the rest of the home directory out, but the granted login profile remains available to that engine.

Impact:
An agent process operating in the granted profile may affect or access the credentials/session state that profile contains, within the provider CLI's own protection model.

Required mitigation:
Use a dedicated OS account and dedicated provider profile for Open Duet. Do not reuse a host account that has OWNERA production credentials or unrelated privileged sessions.

### OD-05 — Engine environment is allow-listed by name, but not scoped to the selected engine

**Risk: High when multiple provider credentials are present in the Open Duet server environment and an untrusted generic ACP command is configured.**

Evidence at the pinned commit:
- `backend/app/core/engine_env.py` puts `GOOGLE_API_KEY` in the unconditional baseline allow-list and unconditionally accepts every environment variable whose name starts with `ANTHROPIC_`, `CLAUDE_`, `CODEX_`, `OPENAI_`, or `GEMINI_`.
- `backend/app/services/acp_adapter.py` implements the generic ACP adapter's `child_env()` by calling `local_claude_runner.child_env()` without provider-specific scoping.
- `backend/app/services/local_claude_runner.py` builds child environments through `engine_environment()`.
- `backend/tests/core/test_engine_env.py` verifies that engine-prefixed names are retained, but does not assert isolation between different engine types.

Impact:
An arbitrary configured ACP executable can inherit provider keys that happen to be present in the backend process environment, even if those keys belong to another provider. The global never-list protects named application secrets such as `TOKEN_ENCRYPTION_KEYS` and `DATABASE_URL`, but it does not make provider credentials mutually isolated. This is a source-confirmed overbroad environment boundary; actual exposure depends on which credentials the operator has set in the backend environment.

Required mitigation:
1. Do not configure an untrusted generic ACP command in a server process that has unrelated provider keys in its environment.
2. Change environment construction to be adapter-specific: generic ACP should receive only a minimal OS/runtime environment plus explicitly configured credentials for that exact engine.
3. Add tests with several synthetic provider keys and assert each adapter receives only its own allow-list; include a malicious fake ACP child that records environment variable *names* and verifies unrelated keys are absent.
4. Keep the application-secret never-list as a separate invariant and test it independently.

## Positive controls observed

- `backend/app/core/host_exec.py` centralizes a `HOST_EXECUTION_DISABLED` check for process launches in hosted mode.
- `backend/app/services/stdio_rpc.py` and `backend/app/services/local_claude_runner.py` call `host_exec.ensure_allowed()` before spawning engine processes.
- The optional Linux sandbox builds explicit mounts, refuses unsupported environments, and has no-unboxed-fallback tests.
- The egress gate rejects non-public destinations, validates DNS answers before connecting to numeric addresses, and has targeted policy/transport tests.
- ACP permission handling denies requests when local tools are off or plan mode is active, and only accepts a one-use approval option.

These controls reduce specific risks; they do not make arbitrary external agent executables trusted or turn the approval UI into an OWNERA financial authorization system.

## Evidence and limitations

- Source references are pinned to `9b67118d9f18de70fbce394093c9c95aeb79045e`.
- Useful source files: [ACP adapter](https://github.com/Anil-matcha/open-duet/blob/9b67118d9f18de70fbce394093c9c95aeb79045e/backend/app/services/acp_adapter.py), [sandbox](https://github.com/Anil-matcha/open-duet/blob/9b67118d9f18de70fbce394093c9c95aeb79045e/backend/app/core/turn_sandbox.py), [egress gate](https://github.com/Anil-matcha/open-duet/blob/9b67118d9f18de70fbce394093c9c95aeb79045e/backend/app/core/turn_egress.py), [sandbox tests](https://github.com/Anil-matcha/open-duet/blob/9b67118d9f18de70fbce394093c9c95aeb79045e/backend/tests/core/test_turn_sandbox.py), [egress tests](https://github.com/Anil-matcha/open-duet/blob/9b67118d9f18de70fbce394093c9c95aeb79045e/backend/tests/core/test_turn_egress.py), [connected-app caveats](https://github.com/Anil-matcha/open-duet/blob/9b67118d9f18de70fbce394093c9c95aeb79045e/docs/CONNECTED_APPS.md).
- This is source inspection only. No dependencies were installed, no process was launched, no test suite was run, and no live-provider behavior was verified.
- No exploit was demonstrated. OD-01 is a trust-boundary limitation confirmed by the implementation's opt-in sandbox and the generic ACP adapter contract; OD-02 is an exposure explicitly documented upstream.
- Reassess this note whenever the submodule pin changes.
