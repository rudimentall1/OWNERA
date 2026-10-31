from __future__ import annotations

import os
import re
import tempfile
from decimal import Decimal

import pytest

from ownera.artifact_registry import SQLiteArtifactRegistry
from ownera.artifact_review import ArtifactReviewService
from ownera.persistent_workforce import PersistentWorkforce
from ownera.quality_gate import CriterionAssessment, QualityGateService
from ownera.worker_execution import WorkerExecutionService
from ownera.worker_runtime import (
    DockerWorkerRuntime,
    RuntimeLimits,
    WorkerExecutionRequest,
    WorkerRuntimeError,
)
from ownera.workforce import TaskStatus, WorkerProfile, WorkTask

IMAGE = os.environ.get("OWNERA_WORKER_IMAGE", "")
pytestmark = pytest.mark.integration


def _runtime(*, limits: RuntimeLimits | None = None) -> DockerWorkerRuntime:
    if not re.fullmatch(r".+@sha256:[0-9a-f]{64}", IMAGE):
        pytest.skip("OWNERA_WORKER_IMAGE must be pinned by a SHA-256 digest")
    return DockerWorkerRuntime(IMAGE, limits=limits)


def _python(*parts: str) -> tuple[str, ...]:
    return ("python", "-I", "-c", *parts)


def test_real_container_has_no_network_access():
    runtime = _runtime()
    result = runtime.execute(
        WorkerExecutionRequest(
            "integration-network",
            _python(
                "import socket\n"
                "assert [name for _, name in socket.if_nameindex()] == ['lo']\n"
                "s=socket.socket()\n"
                "s.settimeout(2)\n"
                "try:\n"
                " s.connect(('1.1.1.1', 53))\n"
                " raise SystemExit(9)\n"
                "except OSError:\n"
                " pass\n"
                "finally:\n"
                " s.close()\n"
                "print('network-denied')"
            ),
        )
    )
    assert result.status == "SUCCEEDED"
    assert "network-denied" in result.stdout


def test_real_container_cannot_read_host_sentinel():
    runtime = _runtime()
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8") as sentinel:
        sentinel.write("OWNERA_HOST_SECRET_SENTINEL")
        sentinel.flush()
        result = runtime.execute(
            WorkerExecutionRequest(
                "integration-host-boundary",
                _python(
                    "from pathlib import Path\n"
                    f"p=Path({sentinel.name!r})\n"
                    "assert not p.exists() or "
                    "'OWNERA_HOST_SECRET_SENTINEL' not in p.read_text()\n"
                    "print('host-sentinel-unavailable')"
                ),
            )
        )
    assert result.status == "SUCCEEDED"
    assert "host-sentinel-unavailable" in result.stdout


def test_real_container_input_is_read_only_and_artifact_is_exported():
    runtime = _runtime()
    result = runtime.execute(
        WorkerExecutionRequest(
            "integration-input-artifact",
            _python(
                "from pathlib import Path\n"
                "source=Path('/inputs/message.txt')\n"
                "assert source.read_text() == 'hello'\n"
                "try:\n"
                " source.write_text('changed')\n"
                " raise SystemExit(8)\n"
                "except OSError:\n"
                " pass\n"
                "Path('/workspace/result.txt').write_text('verified')"
            ),
            input_files={"message.txt": b"hello"},
            artifact_paths=("result.txt",),
        )
    )
    assert result.status == "SUCCEEDED"
    assert result.artifacts == {"result.txt": b"verified"}


def test_real_container_timeout_is_enforced():
    runtime = _runtime(limits=RuntimeLimits(wall_seconds=1))
    result = runtime.execute(
        WorkerExecutionRequest("integration-timeout", _python("import time; time.sleep(10)"))
    )
    assert result.status == "TIMED_OUT"


def test_real_container_output_limit_is_enforced():
    runtime = _runtime(limits=RuntimeLimits(max_output_bytes=4096, wall_seconds=10))
    result = runtime.execute(
        WorkerExecutionRequest(
            "integration-output-limit",
            _python("print('x' * 100_000)"),
        )
    )
    assert result.status == "OUTPUT_LIMIT_EXCEEDED"


def test_real_container_symlink_artifact_is_rejected():
    runtime = _runtime()
    with pytest.raises(WorkerRuntimeError, match="regular file"):
        runtime.execute(
            WorkerExecutionRequest(
                "integration-symlink-artifact",
                _python(
                    "from pathlib import Path\n"
                    "Path('/workspace/leak').symlink_to('/etc/passwd')"
                ),
                artifact_paths=("leak",),
            )
        )


def test_real_container_process_limit_is_enforced():
    runtime = _runtime(limits=RuntimeLimits(pids=64, wall_seconds=15))
    result = runtime.execute(
        WorkerExecutionRequest(
            "integration-pids-limit",
            _python(
                "import subprocess,sys\n"
                "children=[]\n"
                "try:\n"
                " for _ in range(128):\n"
                "  try:\n"
                "   children.append(subprocess.Popen([sys.executable,'-c','import time;time.sleep(20)']))\n"
                "  except OSError:\n"
                "   break\n"
                " assert len(children) < 128\n"
                " print('pids-limited', len(children))\n"
                "finally:\n"
                " for child in children:\n"
                "  child.terminate()\n"
                " for child in children:\n"
                "  child.wait(timeout=3)"
            ),
        )
    )
    assert result.status == "SUCCEEDED"
    assert "pids-limited" in result.stdout


def test_real_container_memory_limit_is_enforced():
    runtime = _runtime(
        limits=RuntimeLimits(
            memory_bytes=256 * 1024 * 1024,
            tmp_bytes=16 * 1024 * 1024,
            wall_seconds=15,
        )
    )
    result = runtime.execute(
        WorkerExecutionRequest(
            "integration-memory-limit",
            _python(
                "chunks=[]\n"
                "while True:\n"
                " chunks.append(bytearray(8 * 1024 * 1024))"
            ),
        )
    )
    assert result.status == "FAILED"
    assert result.exit_code == 137



def test_real_docker_execution_to_registry_review_and_quality_acceptance(tmp_path):
    runtime = _runtime()
    database = tmp_path / "workforce.sqlite3"
    workforce = PersistentWorkforce(database)
    workforce.register_worker(
        WorkerProfile("docker-builder", "backend", frozenset({"python"}))
    )
    workforce.register_worker(
        WorkerProfile("independent-reviewer", "qa", frozenset({"quality.review"}))
    )
    task = WorkTask(
        title="Produce requested output",
        description="Read the input specification and create the requested artifact.",
        required_capabilities=frozenset({"python"}),
        budget_limit=Decimal("10"),
        currency="EUR",
        acceptance_criteria=("Artifact contains the requested output",),
    )
    workforce.add_task(task)
    workforce.assign(task.task_id)
    workforce.start(task.task_id, "docker-builder")

    registry = SQLiteArtifactRegistry(tmp_path / "artifacts.sqlite3")
    execution = WorkerExecutionService(
        runtime=runtime, registry=registry, workforce=workforce
    )
    submission = execution.execute_and_submit(
        WorkerExecutionRequest(
            task_id=str(task.task_id),
            command=(
                "python",
                "-I",
                "-c",
                (
                    "from pathlib import Path; "
                    "spec=Path('/inputs/spec.txt').read_text(); "
                    "Path('/workspace/result.txt').write_text('DELIVERED: '+spec)"
                ),
            ),
            input_files={"spec.txt": b"customer-approved-scope"},
            artifact_paths=("result.txt",),
        ),
        worker_id="docker-builder",
        summary="Created the requested output in an isolated container.",
        actual_cost=Decimal("1"),
    )

    assert submission.runtime_status == "SUCCEEDED"
    assert len(submission.artifact_records) == 1
    artifact = submission.artifact_records[0]
    assert registry.get(artifact.sha256) == b"DELIVERED: customer-approved-scope"

    quality_gate = QualityGateService(
        workforce,
        ArtifactReviewService(registry=registry, workforce=workforce),
    )
    result = quality_gate.review(
        task.task_id,
        "independent-reviewer",
        (
            CriterionAssessment(
                "Artifact contains the requested output",
                True,
                (artifact.sha256,),
                "Inspected the original artifact bytes.",
            ),
        ),
        overall_notes="The submitted artifact matches the approved scope.",
    )

    assert result.accepted is True
    assert result.task_status is TaskStatus.ACCEPTED
    restored = PersistentWorkforce(database)
    assert restored.tasks[0].status is TaskStatus.ACCEPTED
    assert QualityGateService.extract_report(restored.reviews[0])["criteria"][0]["passed"]
