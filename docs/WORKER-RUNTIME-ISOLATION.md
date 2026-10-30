# Worker Runtime Isolation

**Status:** Initial Docker-backed execution adapter implemented; production runner deployment and adversarial validation remain open.  
**Code:** \`ownera/worker_runtime.py\`  
**Tests:** \`tests/test_worker_runtime.py\`

## Purpose

The workforce coordinator persists tasks and enforces assignment, budget, dependency, and independent-review rules. It must not execute worker-supplied code inside the OWNERA API process. This adapter provides a separate execution boundary for one bounded task.

## Runtime contract

A WorkerExecutionRequest contains a task identifier, an argument-vector command, read-only input files, and explicitly requested artifact paths. The runtime returns a status, exit code, bounded stdout/stderr, requested artifact bytes, and elapsed time. It does not invoke a shell and does not inherit caller-supplied environment variables.

The runtime requires a pre-pulled container image pinned by SHA-256 digest. The caller is responsible for selecting and maintaining a trusted image. It does not pull arbitrary images as part of task execution.

## Isolation controls

Each task receives a new container with:

- network disabled (--network none);
- read-only container root filesystem;
- all Linux capabilities dropped;
- no-new-privileges enabled;
- non-root UID/GID 65532;
- CPU, memory, swap, PID, file-size, open-file and wall-clock limits;
- bounded tmpfs workspace and temporary directory;
- a read-only bind mount containing only task input files;
- no host home, project checkout, Docker socket, credentials, or writable host directory mounted into the container;
- no environment variables other than a fixed PATH;
- bounded captured output and explicitly requested artifacts only.

The writable workspace and temporary directory are container tmpfs mounts. Artifacts are copied out only after the container exits. The container is removed in a cleanup path.

## Trust boundary and limitations

The Docker daemon, host kernel, runner administrator, and pinned image are trusted components. This is a container isolation boundary, not a VM or microVM. A kernel/container escape remains possible. Production workloads with hostile multi-tenant code should use dedicated ephemeral runner hosts or a hardened VM/microVM service, not share a general-purpose application host.

This module is not yet connected to PersistentWorkforce. No task is automatically executed, no customer data is currently dispatched, and no secrets or financial capabilities are exposed. The runtime is an opt-in adapter and is not a production deployment claim.

The Docker image must already be available locally. Runtime provisioning, image signature verification, image vulnerability policy, host hardening, concurrency scheduling, per-tenant isolation, metrics, and external penetration testing remain production gates.

## Failure behavior

- Missing Docker CLI: fail closed before task execution.
- Invalid image digest, command, or file path: reject the request.
- Timeout: kill the Docker CLI process group and request container termination.
- Output overflow: terminate the container and report OUTPUT_LIMIT_EXCEEDED.
- Non-zero task exit: return FAILED; do not mark the workforce task accepted.
- Missing, symlinked, non-regular, or oversized requested artifact: reject artifact collection.
- Container cleanup runs even when artifact collection fails.

A successful process exit is not task acceptance. The existing independent reviewer and acceptance criteria remain mandatory.

## Next gates

1. Run this adapter on a dedicated Linux runner with rootless Docker or an equivalent hardened container runtime.
2. Add real-container adversarial tests for network access, host-file access, process exhaustion, memory exhaustion, output flooding, timeout, and artifact path attacks.
3. Verify container termination and cleanup after forced runner/process failure.
4. Add image signature and vulnerability-policy enforcement.
5. Connect execution to the task lifecycle only after runtime acceptance tests pass.
6. Add per-task cost and resource accounting before any autonomous budget expansion.
