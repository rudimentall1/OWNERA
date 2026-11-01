"""Hardened Docker-backed runtime for bounded OWNERA worker tasks.

This adapter is opt-in. It requires a pre-pulled image pinned by SHA-256 digest
and a trusted Docker daemon. It never mounts the Docker socket, host home
directories, credentials, or writable host paths into the container.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
import time
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Protocol
from uuid import uuid4


class WorkerRuntimeError(RuntimeError):
    """Raised when a worker request or runtime result violates its contract."""


class WorkerRuntimeUnavailable(WorkerRuntimeError):
    """Raised when the configured container runtime is unavailable."""


@dataclass(frozen=True)
class RuntimeLimits:
    """Hard upper bounds applied to one worker container."""

    cpu_cores: float = 1.0
    memory_bytes: int = 512 * 1024 * 1024
    wall_seconds: int = 60
    pids: int = 64
    max_output_bytes: int = 1024 * 1024
    max_input_bytes: int = 10 * 1024 * 1024
    max_input_files: int = 256
    max_command_bytes: int = 32 * 1024
    max_artifact_count: int = 64
    max_workspace_bytes: int = 64 * 1024 * 1024
    max_artifact_bytes: int = 10 * 1024 * 1024
    max_artifacts_total_bytes: int = 20 * 1024 * 1024
    tmp_bytes: int = 16 * 1024 * 1024

    def __post_init__(self) -> None:
        if not 0 < self.cpu_cores <= 8:
            raise ValueError("cpu_cores must be in (0, 8]")
        for name in (
            "memory_bytes", "wall_seconds", "pids", "max_output_bytes",
            "max_input_bytes", "max_input_files", "max_command_bytes",
            "max_artifact_count", "max_workspace_bytes", "max_artifact_bytes",
            "max_artifacts_total_bytes", "tmp_bytes",
        ):
            if getattr(self, name) <= 0:
                raise ValueError(f"{name} must be positive")
        if self.max_artifact_bytes > self.max_workspace_bytes:
            raise ValueError("per-artifact limit cannot exceed workspace limit")
        if self.max_artifacts_total_bytes > self.max_workspace_bytes:
            raise ValueError("total artifact limit cannot exceed workspace limit")
        if self.tmp_bytes > self.memory_bytes:
            raise ValueError("tmpfs limit cannot exceed memory limit")


@dataclass(frozen=True)
class WorkerExecutionRequest:
    """A task payload. Input files are copied into a read-only container mount."""

    task_id: str
    command: tuple[str, ...]
    input_files: Mapping[str, bytes] = field(default_factory=dict)
    artifact_paths: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.task_id, str) or not self.task_id.strip():
            raise ValueError("task_id is required")
        if not self.command or any(
            not isinstance(part, str) or not part or "\x00" in part
            for part in self.command
        ):
            raise ValueError("command must contain non-empty strings without NUL")
        if len(self.input_files) > 256:
            raise WorkerRuntimeError("too many input files")
        if len(self.artifact_paths) > 64:
            raise WorkerRuntimeError("too many requested artifacts")
        if sum(len(part.encode("utf-8")) for part in self.command) > 32 * 1024:
            raise WorkerRuntimeError("command exceeds configured byte limit")
        for path in self.input_files:
            _safe_relative_path(path)
        for path in self.artifact_paths:
            _safe_relative_path(path)


@dataclass(frozen=True)
class WorkerExecutionResult:
    """Bounded execution output and explicitly requested artifacts."""

    task_id: str
    status: str
    exit_code: int | None
    stdout: str
    stderr: str
    artifacts: Mapping[str, bytes]
    duration_seconds: float


def _safe_relative_path(value: str) -> PurePosixPath:
    if (
        not isinstance(value, str) or not value or "\x00" in value
        or "\\" in value or value.startswith("/")
        or len(value) > 240
        or len(value.split("/")) > 16
        or any(
            part in ("", ".", "..") or len(part.encode("utf-8")) > 100
            for part in value.split("/")
        )
    ):
        raise WorkerRuntimeError("file paths must be safe relative POSIX paths")
    return PurePosixPath(value)


class WorkerRuntime(Protocol):
    """Provider-neutral contract for bounded task execution."""

    def execute(self, request: WorkerExecutionRequest) -> WorkerExecutionResult:
        """Execute one task and return bounded output and artifacts."""
        ...


class DockerWorkerRuntime:
    """Runs one task in a network-isolated, resource-bounded Docker container.

    The image must be pinned as name@sha256:<64 lowercase hex characters>.
    The Docker daemon and host kernel remain trusted parts of the boundary.
    """

    def __init__(
        self,
        image: str,
        *,
        limits: RuntimeLimits | None = None,
        docker_binary: str = "docker",
    ) -> None:
        if "@sha256:" not in image:
            raise ValueError("worker image must be pinned by sha256 digest")
        digest = image.rsplit("@sha256:", 1)[1]
        if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
            raise ValueError("worker image must contain a valid lowercase sha256 digest")
        if not docker_binary:
            raise ValueError("docker_binary is required")
        self.image = image
        self.limits = limits or RuntimeLimits()
        self.docker_binary = docker_binary

    def execute(self, request: WorkerExecutionRequest) -> WorkerExecutionResult:
        started = time.monotonic()
        docker = self._resolve_docker()
        if any(not isinstance(content, bytes) for content in request.input_files.values()):
            raise WorkerRuntimeError("input file contents must be bytes")
        input_size = sum(len(content) for content in request.input_files.values())
        if input_size > self.limits.max_input_bytes:
            raise WorkerRuntimeError("task inputs exceed configured byte limit")
        if len(request.input_files) > self.limits.max_input_files:
            raise WorkerRuntimeError("task has too many input files")
        if len(request.artifact_paths) > self.limits.max_artifact_count:
            raise WorkerRuntimeError("task requests too many artifacts")
        command_size = sum(len(part.encode("utf-8")) for part in request.command)
        if command_size > self.limits.max_command_bytes:
            raise WorkerRuntimeError("task command exceeds configured byte limit")
        if len(set(request.artifact_paths)) != len(request.artifact_paths):
            raise WorkerRuntimeError("artifact paths must be unique")

        container_name = f"ownera-worker-{uuid4().hex}"
        with tempfile.TemporaryDirectory(prefix="ownera-input-") as input_dir:
            input_root = Path(input_dir)
            if ".ownera-worker-wrapper.sh" in request.input_files:
                raise WorkerRuntimeError("input path is reserved for the worker wrapper")
            self._stage_inputs(input_root, request.input_files)
            wrapper = input_root / ".ownera-worker-wrapper.sh"
            wrapper.write_text(
                "#!/bin/sh\n"
                "set +e\n"
                "\"$@\" > /workspace/.ownera_stdout 2> /workspace/.ownera_stderr\n"
                "result=$?\n"
                "printf \"%s\" \"$result\" > /workspace/.ownera_exit\n"
                "sleep 600\n"
                "exit \"$result\"\n",
                encoding="utf-8",
            )
            wrapper.chmod(0o444)
            args = self._container_args(docker, container_name, input_root, request.command)
            status = "FAILED"
            exit_code = None
            stdout = b""
            stderr = b""
            artifacts: dict[str, bytes] = {}
            try:
                status, exit_code, stdout, stderr = self._run_container(
                    args, container_name, self.limits.wall_seconds
                )
                if status == "SUCCEEDED":
                    artifacts = self._collect_artifacts(
                        docker, container_name, request.artifact_paths
                    )
            finally:
                self._cleanup_container(docker, container_name)

        return WorkerExecutionResult(
            task_id=request.task_id,
            status=status,
            exit_code=exit_code,
            stdout=stdout.decode("utf-8", errors="replace"),
            stderr=stderr.decode("utf-8", errors="replace"),
            artifacts=artifacts,
            duration_seconds=max(0.0, time.monotonic() - started),
        )

    def _resolve_docker(self) -> str:
        resolved = shutil.which(self.docker_binary)
        if resolved is None:
            raise WorkerRuntimeUnavailable("Docker CLI was not found")
        return resolved

    def _stage_inputs(self, root: Path, files: Mapping[str, bytes]) -> None:
        # The container runs as UID 65532; the mounted root must be traversable.
        root.chmod(0o755)
        for name, content in files.items():
            if not isinstance(content, bytes):
                raise WorkerRuntimeError("input file contents must be bytes")
            relative = _safe_relative_path(name)
            destination = root.joinpath(*relative.parts)
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(content)
            destination.chmod(0o444)

    def _container_args(
        self, docker: str, name: str, input_root: Path, command: tuple[str, ...]
    ) -> list[str]:
        limits = self.limits
        return [
            docker, "run", "-d", "--pull=never", "--name", name,
            "--network", "none",
            "--read-only",
            "--cap-drop", "ALL",
            "--security-opt", "no-new-privileges",
            "--pids-limit", str(limits.pids),
            "--memory", str(limits.memory_bytes),
            "--memory-swap", str(limits.memory_bytes),
            "--cpus", str(limits.cpu_cores),
            "--ulimit", f"fsize={limits.max_artifact_bytes}:{limits.max_artifact_bytes}",
            "--ulimit", "nofile=64:64",
            "--user", "65532:65532",
            "--workdir", "/workspace",
            "--mount", f"type=bind,src={input_root},dst=/inputs,readonly",
            "--tmpfs", f"/workspace:rw,nosuid,nodev,size={limits.max_workspace_bytes},uid=65532,gid=65532,mode=1770",
            "--tmpfs", f"/tmp:rw,noexec,nosuid,nodev,size={limits.tmp_bytes},uid=65532,gid=65532,mode=1777",
            "--env", "PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
            "--log-driver", "none",
            self.image, "sh", "/inputs/.ownera-worker-wrapper.sh", *command,
        ]

    def _run_container(
        self, args: list[str], container_name: str, timeout: int
    ) -> tuple[str, int | None, bytes, bytes]:
        docker = args[0]
        launched = subprocess.run(
            args, stdin=subprocess.DEVNULL, capture_output=True,
            timeout=30, check=False,
        )
        if launched.returncode != 0:
            return "FAILED", launched.returncode, launched.stdout, launched.stderr

        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            marker = subprocess.run(
                [docker, "exec", container_name, "sh", "-c",
                 "test -f /workspace/.ownera_exit"],
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL, timeout=5, check=False,
            )
            if marker.returncode == 0:
                break
            state = subprocess.run(
                [docker, "inspect", "--format", "{{.State.Running}}", container_name],
                stdin=subprocess.DEVNULL, capture_output=True, timeout=5, check=False,
            )
            if state.returncode != 0 or state.stdout.strip() != b"true":
                exit_result = subprocess.run(
                    [docker, "inspect", "--format", "{{.State.ExitCode}}", container_name],
                    stdin=subprocess.DEVNULL, capture_output=True, timeout=5, check=False,
                )
                try:
                    exit_code = int(exit_result.stdout.strip())
                except ValueError:
                    exit_code = None
                return (
                    "FAILED", exit_code, b"",
                    b"worker container exited before writing its completion marker; image must provide /bin/sh and sleep",
                )
            time.sleep(0.1)
        else:
            self._stop_container(docker, container_name)
            return "TIMED_OUT", None, b"", b"worker execution exceeded its wall-time limit"

        def read_container_file(path: str) -> bytes:
            result = subprocess.run(
                [docker, "exec", container_name, "cat", path],
                stdin=subprocess.DEVNULL, capture_output=True, timeout=10, check=False,
            )
            if result.returncode != 0:
                raise WorkerRuntimeError(f"could not read worker output: {path}")
            return result.stdout

        try:
            exit_code = int(read_container_file("/workspace/.ownera_exit").strip())
        except ValueError as exc:
            raise WorkerRuntimeError("worker completion marker is invalid") from exc
        stdout = read_container_file("/workspace/.ownera_stdout")
        stderr = read_container_file("/workspace/.ownera_stderr")
        if len(stdout) + len(stderr) > self.limits.max_output_bytes:
            return (
                "OUTPUT_LIMIT_EXCEEDED", exit_code,
                stdout[:self.limits.max_output_bytes], b"worker output exceeded configured limit",
            )
        return ("SUCCEEDED" if exit_code == 0 else "FAILED", exit_code, stdout, stderr)

    @staticmethod
    def _stop_container(docker: str, name: str) -> None:
        try:
            subprocess.run(
                [docker, "kill", name], stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                timeout=5, check=False,
            )
        except subprocess.TimeoutExpired:
            pass

    def _collect_artifacts(
        self, docker: str, container_name: str, paths: tuple[str, ...]
    ) -> dict[str, bytes]:
        artifacts: dict[str, bytes] = {}
        total = 0

        def check(path: str, predicate: str) -> bool:
            result = subprocess.run(
                [docker, "exec", container_name, "sh", "-c",
                 f"test {predicate} \"$1\"", "sh", path],
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL, timeout=10, check=False,
            )
            return result.returncode == 0

        for name in paths:
            relative = _safe_relative_path(name)
            current = PurePosixPath("/workspace")
            for index, part in enumerate(relative.parts):
                current = current / part
                path = str(current)
                if check(path, "-L"):
                    raise WorkerRuntimeError(
                        f"artifact path contains a symbolic link: {name}"
                    )
                predicate = "-d" if index < len(relative.parts) - 1 else "-f"
                if not check(path, predicate):
                    if index < len(relative.parts) - 1:
                        raise WorkerRuntimeError(
                            f"artifact parent is not a directory: {name}"
                        )
                    raise WorkerRuntimeError(f"requested artifact is missing: {name}")

            size_result = subprocess.run(
                [docker, "exec", container_name, "sh", "-c",
                 "wc -c < \"$1\"", "sh", str(current)],
                stdin=subprocess.DEVNULL, capture_output=True, timeout=10, check=False,
            )
            if size_result.returncode != 0:
                raise WorkerRuntimeError(f"could not inspect requested artifact: {name}")
            try:
                size = int(size_result.stdout.strip())
            except ValueError as exc:
                raise WorkerRuntimeError(f"artifact size response is invalid: {name}") from exc
            if size > self.limits.max_artifact_bytes:
                raise WorkerRuntimeError(f"artifact exceeds size limit: {name}")
            total += size
            if total > self.limits.max_artifacts_total_bytes:
                raise WorkerRuntimeError("artifacts exceed total byte limit")

            content_result = subprocess.run(
                [docker, "exec", container_name, "cat", str(current)],
                stdin=subprocess.DEVNULL, capture_output=True, timeout=10, check=False,
            )
            if content_result.returncode != 0:
                raise WorkerRuntimeError(f"could not read requested artifact: {name}")
            if len(content_result.stdout) != size:
                raise WorkerRuntimeError(f"artifact changed while being collected: {name}")
            artifacts[name] = content_result.stdout
        return artifacts

    def _cleanup_container(self, docker: str, name: str) -> None:
        try:
            subprocess.run(
                [docker, "rm", "-f", name], stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                timeout=10, check=False,
            )
        except subprocess.TimeoutExpired:
            pass
