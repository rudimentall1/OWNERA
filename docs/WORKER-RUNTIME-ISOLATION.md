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
- no caller or host environment variables are forwarded; PATH is explicitly set. Environment declared inside the pinned image remains part of the trusted image;
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

## Real-container acceptance harness

A manually triggered GitHub Actions workflow is available at
`.github/workflows/worker-runtime-integration.yml`. It accepts only a worker
image reference pinned by a lowercase SHA-256 digest, pulls that exact image,
and runs the opt-in tests in `tests/integration/test_docker_worker_runtime.py`.

Run it from GitHub Actions → Worker Runtime Integration → Run workflow. Supply
a trusted image reference in the form `repository/image:tag@sha256:<64 hex>`.
The image must contain Python 3 and must be trusted by the operator. The workflow
does not choose or silently update the image.

The integration suite exercises real Docker behavior for network isolation, host-file separation, read-only inputs, artifact export,
process and memory limits, timeout, output limits, and symlink-artifact rejection.
It now also includes a full vertical-slice test: real container execution, content-addressed artifact registration, independent artifact loading, criterion-level Quality Gate review, and persisted task acceptance. This test is present but has not yet been run against a live Docker daemon. These tests are not part of the default unit
suite because they require a Docker daemon and an explicitly selected image.
A successful workflow run is evidence for that exact image and runner
configuration only; it is not a general proof against kernel or daemon escapes.
For a reproducible initial harness run, the Docker Official Image `python:3.11.18-slim-bookworm` was observed with multi-platform index digest `sha256:ef521de1d817dc92a6358c906bbadb9a0b7e38040038642833521b9d582c2233` on 2026-10-31 ([Docker Hub image details](https://hub.docker.com/layers/library/python/3.11.18-slim-bookworm/images/sha256-061c190f3d5815b341a18dfe8a45771f8ba68c15a607ea56997fde3009ac4eec)). This is a functional test baseline only, not a production-approved hardened image.


## Next gates

1. Run the real-container workflow with a reviewed, digest-pinned Python image.
2. Add forced runner/process-failure cleanup tests and verify container removal after host-side interruption.
3. Verify the runner uses rootless Docker or an equivalent hardened runtime on a dedicated Linux host.
4. Add image signature verification and vulnerability-policy enforcement.
5. Connect execution to the task lifecycle only after runtime acceptance tests pass.
6. Add per-task cost and resource accounting before any autonomous budget expansion.
