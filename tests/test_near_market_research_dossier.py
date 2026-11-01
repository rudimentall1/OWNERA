import hashlib
import sqlite3
from email.message import Message

import pytest

from ownera.artifact_registry import ArtifactIntegrityError, SQLiteArtifactRegistry
from ownera.near_market_assignments import sync_assignments
from ownera.near_market_research_dossier import (
    ResearchDossierError,
    build_active_assignment_dossiers,
    build_assignment_dossier,
)
from ownera.near_market_source_collector import collect_assignment_sources


class Response:
    status = 200
    def __init__(self, body, url):
        self.body, self.url = body, url
        self.headers = Message()
        self.headers["Content-Type"] = "text/html; charset=utf-8"
    def __enter__(self): return self
    def __exit__(self, *args): return False
    def read(self, size=-1): return self.body if size < 0 else self.body[:size]
    def geturl(self): return self.url


class Opener:
    def open(self, request, timeout=0):
        url = request.full_url
        if url.endswith("/robots.txt"):
            return Response(b"User-agent: *\nAllow: /\n", url)
        body = f"<html><head><title>Evidence {url}</title></head><body><main><p>Public evidence captured from {url}.</p></main></body></html>".encode()
        return Response(body, url)


@pytest.fixture
def public_dns(monkeypatch):
    monkeypatch.setattr("ownera.near_market_source_collector.socket.getaddrinfo", lambda host, port, type=None: [(None, None, None, None, ("93.184.216.34", port))])


def _setup(db_path):
    item = {
        "assignment": {"assignmentId": "dossier-assignment-1", "jobId": "dossier-job-1", "status": "in_progress", "startedAt": "2026-11-01T12:00:00Z"},
        "job": {"jobId": "dossier-job-1", "title": "Find SageKai Agent", "description": "Use public sources and report exact match."},
    }
    sync_assignments(db_path, assignments=[item])


def test_dossier_links_citations_to_verified_original_bytes(tmp_path, public_dns):
    db = tmp_path / "ownera.sqlite3"
    _setup(db)
    collect_assignment_sources(db, "dossier-assignment-1", opener=Opener())
    result = build_assignment_dossier(db, "dossier-assignment-1")
    assert result["execution_state"] == "EVIDENCE_DOSSIER_ONLY"
    assert result["semantic_review"] == "NOT_PERFORMED"
    assert result["acceptance_criteria"] == "NOT_ASSESSED"
    registry = SQLiteArtifactRegistry(db)
    record = next(x for x in registry.list_for_task(result["task_id"]) if x.artifact_name == "RESEARCH_DOSSIER.md")
    text = registry.get(record.sha256).decode()
    assert "[S1]" in text and "[S2]" in text
    assert "NOT YET PRODUCED" in text and "NOT ASSESSED" in text
    assert result["artifact_sha256"] == hashlib.sha256(text.encode()).hexdigest()


def test_dossier_rejects_corrupted_source_metadata_or_raw_bytes(tmp_path, public_dns):
    db = tmp_path / "ownera.sqlite3"
    _setup(db)
    collect_assignment_sources(db, "dossier-assignment-1", opener=Opener())
    registry = SQLiteArtifactRegistry(db)
    task_id = "nearresearch-" + hashlib.sha256(b"dossier-assignment-1").hexdigest()[:32]
    raw = next(x for x in registry.list_for_task(task_id) if x.artifact_name == "source-01.raw")
    with sqlite3.connect(db) as conn:
        conn.execute("UPDATE worker_artifact_blobs SET content=? WHERE sha256=?", (b"tampered", raw.sha256))
    with pytest.raises(ArtifactIntegrityError):
        build_assignment_dossier(db, "dossier-assignment-1")


def test_dossier_requires_captured_sources_before_building(tmp_path):
    db = tmp_path / "ownera.sqlite3"
    _setup(db)
    with pytest.raises(ResearchDossierError, match="no verified captured"):
        build_assignment_dossier(db, "dossier-assignment-1")
    assert build_active_assignment_dossiers(db)["dossiers"] == []
