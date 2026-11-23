# OWNERA / OpenClaw Control Center checkpoint — 2026-11-23 (UTC+5)

## Purpose
This checkpoint records the current OpenClaw dashboard and agent-orchestration state. OpenClaw is an operator-facing interface experiment, not yet the production OWNERA workforce orchestrator. It does not supersede OWNERA's independent specialist / Marketplace architecture.

## Verified server state
- Host: `Gensyn2.play2go.cloud` (`77.239.125.37`).
- OpenClaw CLI observed: `2026.11.6`.
- User service `openclaw-gateway.service` was active during the latest server inspection.
- Gateway is loopback-bound at `127.0.0.1:18789`. Operator access: `ssh -N -L 18789:127.0.0.1:18789 root@77.239.125.37`, then browse to `http://127.0.0.1:18789/`.
- `openclaw config validate` returned `Config valid: ~/.openclaw/openclaw.json`.
- Main workspace: `/root/.openclaw/workspace-main-lean`; `AGENTS.md` exists.
- `agents.defaults.skills=[]` is configured to reduce prompt overhead.
- Main model: `groq/openai/gpt-oss-20b`, `maxTokens=4096`. Plain-text response smoke test passed.
- Worker workspace exists at `/opt/OWNERA/agent-workspace/worker`. It was previously configured as a bounded Docker sandbox with network disabled. Preserve this boundary.

## Capability status
| Capability | Status |
|---|---|
| Gateway and dashboard | Reachability confirmed in prior operator session; gateway active in latest inspection. |
| Main plain-text response | Verified. |
| Main reading its workspace file through its own tool | Not verified; a test timed out without returning file content. |
| Main tool calling | Unreliable; a delegation attempt failed with `tool_use_failed` / JSON argument parsing rejection. |
| Direct Worker execution | Not verified by the latest smoke test; no usable result was returned in the captured output window. |
| Main → Worker delegation | Not verified. |
| Main host command execution | Not enabled/verified. |
| OWNERA durable queue, task state, execution logs | Not yet implemented/verified as a complete product workflow. |

## Latest blocker
The most recent tool-use attempt returned:
`LLM request rejected: to parse tool call arguments as JSON | tool_use_failed`.
This proves a tool-call failure, not its root cause. The cause may be provider/model output formatting, OpenClaw adapter behavior, or a tool-schema interaction. Do not assert a definitive diagnosis without a minimal reproduction. Do not switch the working Main model blindly.

## Engineering direction
1. Reproduce the failure with one harmless tool having a minimal schema; retain a redacted trace and exact versions.
2. Test direct Worker execution independently. Create a small file inside the Worker sandbox, read it back, and verify exact bytes/path from the host-side test harness.
3. Test Main → Worker handoff separately using a unique task ID and durable result record.
4. Build an OWNERA-owned task API with validated task schema, persistent queue/state, bounded executor adapter, structured result and evidence. Treat OpenClaw as a replaceable UI/provider adapter, not the source of task truth.
5. Add focused tests for task creation, state transitions, authorization, timeout/failure behavior, idempotency, and result/evidence persistence.
6. Integrate the dashboard with the OWNERA task API only after the backend execution path passes.

## Safety and repository notes
- Do not give Main unrestricted host/root shell access. Keep Worker sandboxed and least-privileged.
- A Gateway auth token was previously exposed in chat. Treat it as compromised and rotate it through the supported OpenClaw procedure before production exposure. Never print credentials.
- On the server, OWNERA repo path is `/opt/OWNERA`, remote `git@github.com:rudimentall1/OWNERA.git`, branch `feat/commercial-evidence-registry`.
- At inspection, the server working tree contained extensive pre-existing modified and untracked files, and the branch was 10 commits ahead of origin. Preserve these changes. Do not reset/clean, broadly stage, or push that branch as a side effect of publishing this checkpoint.
- This checkpoint update changed documentation only. No OWNERA application code, OpenClaw configuration, credentials, systemd units, or running services were modified/restarted.

## Honest current status
Dashboard + Main text chat are operational. A verified autonomous execution/delegation loop is not yet operational. No new autonomous customer delivery, acceptance, or revenue is claimed.
