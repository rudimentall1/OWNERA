from __future__ import annotations

from ownera.worker_runtime import (
    DockerWorkerRuntime,
    RuntimeLimits,
    WorkerExecutionRequest,
    WorkerRuntimeError,
    WorkerRuntimeUnavailable,
)

IMAGE = "python:3.12-slim@sha256:" + ("a" * 64)


def test_runtime_requires_digest_pinned_image():
    import pytest
    with pytest.raises(ValueError, match="pinned by sha256"):
        DockerWorkerRuntime("python:latest")


def test_runtime_rejects_invalid_digest():
    import pytest
    with pytest.raises(ValueError, match="valid lowercase sha256"):
        DockerWorkerRuntime("python:3.12@sha256:bad")


def test_runtime_limits_validate_relationships():
    import pytest
    with pytest.raises(ValueError, match="tmpfs limit"):
        RuntimeLimits(memory_bytes=1024, tmp_bytes=2048)


def test_request_rejects_path_traversal():
    import pytest
    with pytest.raises(WorkerRuntimeError, match="safe relative"):
        WorkerExecutionRequest(
            task_id="task-1", command=("python", "-V"),
            input_files={"../secret": b"no"},
        )


def test_request_rejects_absolute_artifact_path():
    import pytest
    with pytest.raises(WorkerRuntimeError, match="safe relative"):
        WorkerExecutionRequest(
            task_id="task-1", command=("python", "-V"),
            artifact_paths=("/etc/passwd",),
        )


def test_runtime_fails_when_docker_is_missing(monkeypatch):
    import pytest
    monkeypatch.setattr("ownera.worker_runtime.shutil.which", lambda _: None)
    runtime = DockerWorkerRuntime(IMAGE)
    with pytest.raises(WorkerRuntimeUnavailable, match="not found"):
        runtime.execute(WorkerExecutionRequest("task-1", ("python", "-V")))


def test_container_has_no_network_or_host_writable_mount(monkeypatch):
    runtime = DockerWorkerRuntime(IMAGE)
    monkeypatch.setattr(runtime, "_resolve_docker", lambda: "/usr/bin/docker")
    captured = {}

    def run(args, name, timeout):
        captured["args"] = args
        captured["timeout"] = timeout
        return "SUCCEEDED", 0, b"ok", b""

    monkeypatch.setattr(runtime, "_run_container", run)
    monkeypatch.setattr(runtime, "_collect_artifacts", lambda *args: {})
    monkeypatch.setattr(runtime, "_cleanup_container", lambda *args: None)
    result = runtime.execute(
        WorkerExecutionRequest(
            "task-1", ("python", "-I", "-c", "print('ok')"),
            input_files={"src/main.py": b"print('hello')"},
        )
    )
    args = captured["args"]
    assert "--pull=never" in args
    assert args[args.index("--network") + 1] == "none"
    assert "--read-only" in args
    assert args[args.index("--cap-drop") + 1] == "ALL"
    assert args[args.index("--security-opt") + 1] == "no-new-privileges"
    assert "--memory" in args and "--cpus" in args and "--pids-limit" in args
    assert "--tmpfs" in args
    assert "dst=/inputs,readonly" in args[args.index("--mount") + 1]
    assert "/var/run/docker.sock" not in " ".join(args)
    assert result.status == "SUCCEEDED"
    assert result.stdout == "ok"
    assert captured["timeout"] == runtime.limits.wall_seconds


def test_input_limit_is_enforced_before_container_start(monkeypatch):
    import pytest
    runtime = DockerWorkerRuntime(IMAGE, limits=RuntimeLimits(max_input_bytes=3))
    monkeypatch.setattr(runtime, "_resolve_docker", lambda: "/usr/bin/docker")
    with pytest.raises(WorkerRuntimeError, match="inputs exceed"):
        runtime.execute(
            WorkerExecutionRequest("task-1", ("python", "-V"), {"input": b"four"})
        )


def test_artifact_copy_is_bounded_and_returned(monkeypatch):
    runtime = DockerWorkerRuntime(IMAGE)
    monkeypatch.setattr(runtime, "_resolve_docker", lambda: "/usr/bin/docker")
    monkeypatch.setattr(
        runtime, "_run_container", lambda *args: ("SUCCEEDED", 0, b"", b"")
    )
    monkeypatch.setattr(runtime, "_cleanup_container", lambda *args: None)
    monkeypatch.setattr(
        runtime, "_collect_artifacts", lambda *args: {"report/result.txt": b"verified"}
    )
    result = runtime.execute(
        WorkerExecutionRequest(
            "task-2", ("python", "-V"), artifact_paths=("report/result.txt",)
        )
    )
    assert result.artifacts == {"report/result.txt": b"verified"}


def test_nonzero_container_exit_is_reported_as_failure(monkeypatch):
    runtime = DockerWorkerRuntime(IMAGE)
    monkeypatch.setattr(runtime, "_resolve_docker", lambda: "/usr/bin/docker")
    monkeypatch.setattr(
        runtime, "_run_container", lambda *args: ("FAILED", 17, b"", b"error")
    )
    monkeypatch.setattr(runtime, "_cleanup_container", lambda *args: None)
    result = runtime.execute(WorkerExecutionRequest("task-3", ("python", "-V")))
    assert result.status == "FAILED"
    assert result.exit_code == 17
    assert result.stderr == "error"


def test_stage_inputs_writes_read_only_files(tmp_path):
    runtime = DockerWorkerRuntime(IMAGE)
    runtime._stage_inputs(tmp_path, {"nested/input.txt": b"safe"})
    staged = tmp_path / "nested" / "input.txt"
    assert staged.read_bytes() == b"safe"
    assert staged.stat().st_mode & 0o777 == 0o444
    assert tmp_path.stat().st_mode & 0o777 == 0o755


def test_cleanup_runs_when_artifact_collection_fails(monkeypatch):
    import pytest
    runtime = DockerWorkerRuntime(IMAGE)
    monkeypatch.setattr(runtime, "_resolve_docker", lambda: "/usr/bin/docker")
    monkeypatch.setattr(
        runtime, "_run_container", lambda *args: ("SUCCEEDED", 0, b"", b"")
    )
    cleaned = []
    monkeypatch.setattr(
        runtime, "_collect_artifacts",
        lambda *args: (_ for _ in ()).throw(WorkerRuntimeError("bad artifact")),
    )
    monkeypatch.setattr(runtime, "_cleanup_container", lambda *args: cleaned.append(True))
    with pytest.raises(WorkerRuntimeError, match="bad artifact"):
        runtime.execute(
            WorkerExecutionRequest(
                "task-4", ("python", "-V"), artifact_paths=("result.txt",)
            )
        )
    assert cleaned == [True]


def test_artifact_collection_rejects_symlinked_parent_directory(monkeypatch, tmp_path):
    from types import SimpleNamespace

    runtime = DockerWorkerRuntime(IMAGE)
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.txt").write_text("hostile target", encoding="utf-8")

    def fake_run(args, **kwargs):
        destination = __import__("pathlib").Path(args[-1])
        (destination / "linked").symlink_to(outside, target_is_directory=True)
        return SimpleNamespace(returncode=0, stdout=b"", stderr=b"")

    monkeypatch.setattr("ownera.worker_runtime.subprocess.run", fake_run)

    with pytest.raises(WorkerRuntimeError, match="symbolic link"):
        runtime._collect_artifacts(
            "/usr/bin/docker", "container-id", ("linked/secret.txt",)
        )


def test_artifact_collection_rejects_symlinked_final_file(monkeypatch, tmp_path):
    from types import SimpleNamespace
    from pathlib import Path

    runtime = DockerWorkerRuntime(IMAGE)
    outside = tmp_path / "secret.txt"
    outside.write_text("hostile target", encoding="utf-8")

    def fake_run(args, **kwargs):
        destination = Path(args[-1])
        (destination / "leak.txt").symlink_to(outside)
        return SimpleNamespace(returncode=0, stdout=b"", stderr=b"")

    monkeypatch.setattr("ownera.worker_runtime.subprocess.run", fake_run)

    with pytest.raises(WorkerRuntimeError, match="symbolic link"):
        runtime._collect_artifacts(
            "/usr/bin/docker", "container-id", ("leak.txt",)
        )


def test_artifact_collection_copies_workspace_once_and_returns_regular_file(
    monkeypatch, tmp_path
):
    from types import SimpleNamespace
    from pathlib import Path

    runtime = DockerWorkerRuntime(IMAGE)
    calls = []

    def fake_run(args, **kwargs):
        calls.append(args)
        destination = Path(args[-1])
        (destination / "report").mkdir()
        (destination / "report" / "result.txt").write_bytes(b"verified")
        return SimpleNamespace(returncode=0, stdout=b"", stderr=b"")

    monkeypatch.setattr("ownera.worker_runtime.subprocess.run", fake_run)

    result = runtime._collect_artifacts(
        "/usr/bin/docker", "container-id", ("report/result.txt",)
    )

    assert result == {"report/result.txt": b"verified"}
    assert len(calls) == 1
    assert calls[0][2] == "container-id:/workspace/."
