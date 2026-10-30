"""Hardened Docker-backed runtime for bounded OWNERA worker tasks.

This adapter is opt-in. It requires a pre-pulled image pinned by SHA-256 digest
and a trusted Docker daemon. It never mounts the Docker socket, host home
directories, credentials, or writable host paths into the container.
"""

from __future__ import annotations

import os
import selectors
import shutil
import signal
import subprocess
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Mapping
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
    max_workspace_bytes: int = 64 * 1024 * 1024
    max_artifact_bytes: int = 10 * 1024 * 1024
    max_artifacts_total_bytes: int = 20 * 1024 * 1024
    tmp_bytes: int = 16 * 1024 * 1024

    def __post_init__(self) -> None:
        if not 0 < self.cpu_cores <= 8:
            raise ValueError("cpu_cores must be in (0, 8]")
        for name in (
            "memory_bytes", "wall_seconds", "pids", "max_output_bytes",
            "max_input_bytes", "max_workspace_bytes", "max_artifact_bytes",
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
        or any(part in ("", ".", "..") for part in value.split("/"))
    ):
        raise WorkerRuntimeError("file paths must be safe relative POSIX paths")
    return PurePosixPath(value)


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
        if len(set(request.artifact_paths)) != len(request.artifact_paths):
            raise WorkerRuntimeError("artifact paths must be unique")

        container_name = f"ownera-worker-{uuid4().hex}"
        with tempfile.TemporaryDirectory(prefix="ownera-input-") as input_dir:
            input_root = Path(input_dir)
            self._stage_inputs(input_root, request.input_files)
            args = self._container_args(docker, container_name, input_root, request.command)
            status, exit_code, stdout, stderr = self._run_container(
                args, container_name, self.limits.wall_seconds
            )
            artifacts: dict[str, bytes] = {}
            try:
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
            docker, "run", "--name", name,
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
            "--tmpfs", f"/workspace:rw,nosuid,nodev,size={limits.max_workspace_bytes}",
            "--tmpfs", f"/tmp:rw,noexec,nosuid,nodev,size={limits.tmp_bytes}",
            "--env", "PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
            "--log-driver", "none",
            self.image, *command,
        ]

    def _run_container(
        self, args: list[str], container_name: str, timeout: int
    ) -> tuple[str, int | None, bytes, bytes]:
        process = subprocess.Popen(
            args, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, start_new_session=True, close_fds=True,
        )
        assert process.stdout is not None and process.stderr is not None
        selector = selectors.DefaultSelector()
        buffers = {"stdout": bytearray(), "stderr": bytearray()}
        selector.register(process.stdout, selectors.EVENT_READ, "stdout")
        selector.register(process.stderr, selectors.EVENT_READ, "stderr")
        deadline = time.monotonic() + timeout
        status = "SUCCEEDED"
        try:
            while selector.get_map() or process.poll() is None:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    status = "TIMED_OUT"
                    self._kill_process_group(process)
                    self._stop_container(self._resolve_docker(), container_name)
                    break
                for key, _ in selector.select(min(remaining, 0.1)):
                    chunk = os.read(key.fileobj.fileno(), 65536)
                    if not chunk:
                        selector.unregister(key.fileobj)
                        key.fileobj.close()
                        continue
                    total = len(buffers["stdout"]) + len(buffers["stderr"])
                    available = max(0, self.limits.max_output_bytes - total)
                    buffers[key.data].extend(chunk[:available])
                    if len(chunk) > available:
                        status = "OUTPUT_LIMIT_EXCEEDED"
                        self._kill_process_group(process)
                        self._stop_container(self._resolve_docker(), container_name)
                        break
                if status != "SUCCEEDED":
                    break
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self._kill_process_group(process)
                process.wait(timeout=2)
        finally:
            selector.close()
            for stream in (process.stdout, process.stderr):
                if not stream.closed:
                    stream.close()
        if status == "SUCCEEDED" and process.returncode != 0:
            status = "FAILED"
        return status, process.returncode, bytes(buffers["stdout"]), bytes(buffers["stderr"])

    @staticmethod
    def _kill_process_group(process: subprocess.Popen) -> None:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass

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
        with tempfile.TemporaryDirectory(prefix="ownera-artifacts-") as output_dir:
            root = Path(output_dir)
            for name in paths:
                relative = _safe_relative_path(name)
                destination = root.joinpath(*relative.parts)
                destination.parent.mkdir(parents=True, exist_ok=True)
                copied = subprocess.run(
                    [
                        docker, "cp",
                        f"{container_name}:/workspace/{relative.as_posix()}",
                        str(destination),
                    ],
                    stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE, timeout=15, check=False,
                )
                if copied.returncode != 0:
                    raise WorkerRuntimeError(f"requested artifact is missing: {name}")
                metadata = destination.lstat()
                if destination.is_symlink() or not destination.is_file():
                    raise WorkerRuntimeError(f"artifact is not a regular file: {name}")
                if metadata.st_size > self.limits.max_artifact_bytes:
                    raise WorkerRuntimeError(f"artifact exceeds size limit: {name}")
                content = destination.read_bytes()
                total += len(content)
                if total > self.limits.max_artifacts_total_bytes:
                    raise WorkerRuntimeError("artifacts exceed total byte limit")
                artifacts[name] = content
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
