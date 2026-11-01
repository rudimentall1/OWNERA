import hashlib
import json
import sqlite3
from email.message import Message

import pytest

from ownera.near_market_assignments import sync_assignments
from ownera.near_market_source_collector import (
    SourceCollectionError,
    collect_active_assignment_sources,
    collect_assignment_sources,
    fetch_public_source,
)


class FakeResponse:
    def __init__(self, body, *, content_type="text/html; charset=utf-8", url=None, status=200):
        self._body = body
        self.status = status
        self.headers = Message()
        self.headers["Content-Type"] = content_type
        self._url = url

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, size=-1):
        return self._body if size < 0 else self._body[:size]

    def geturl(self):
        return self._url


class FakeOpener:
    def __init__(self, response):
        self.response = response
        self.requests = []

    def open(self, request, timeout=0):
        self.requests.append((request, timeout))
        return FakeResponse(
            self.response._body,
            content_type=self.response.headers.get("Content-Type"),
            url=self.response._url or request.full_url,
            status=self.response.status,
        )


@pytest.fixture
def public_dns(monkeypatch):
    monkeypatch.setattr(
        "ownera.near_market_source_collector.socket.getaddrinfo",
        lambda host, port, type=None: [(None, None, None, None, ("93.184.216.34", port))],
    )


def _active_assignment(db_path, title, description="Use public sources."):
    item = {
        "assignment": {
            "assignmentId": "research-collector-1",
            "jobId": "job-collector-1",
            "status": "in_progress",
            "startedAt": "2026-11-01T12:00:00Z",
        },
        "job": {
            "jobId": "job-collector-1",
            "title": title,
            "description": description,
        },
    }
    sync_assignments(db_path, assignments=[item])
    return item


def test_fetch_public_html_extracts_text_and_hashes_raw_bytes(public_dns):
    url = "https://docs.cdp.coinbase.com/x402/welcome"
    body = b"<html><head><title>Payments</title><script>ignore()</script></head><body><nav>Menu</nav><main><h1>x402</h1><p>Public payments.</p></main></body></html>"
    opener = FakeOpener(FakeResponse(body, url=url))
    result = fetch_public_source(url, approved_urls={url}, opener=opener)
    assert result.title == "Payments"
    assert "x402" in result.text and "Public payments." in result.text
    assert "ignore()" not in result.text and "Menu" not in result.text
    assert result.sha256 == hashlib.sha256(body).hexdigest()
    assert opener.requests[0][0].get_header("User-agent").startswith("OWNERA-ResearchBot/")


def test_fetch_public_source_rejects_urls_not_in_trusted_plan(public_dns):
    url = "https://docs.cdp.coinbase.com/x402/welcome"
    with pytest.raises(SourceCollectionError, match="not present"):
        fetch_public_source(url, approved_urls={"https://example.com/"})


def test_fetch_public_source_rejects_non_public_dns(public_dns, monkeypatch):
    url = "https://docs.cdp.coinbase.com/x402/welcome"
    monkeypatch.setattr(
        "ownera.near_market_source_collector.socket.getaddrinfo",
        lambda *args, **kwargs: [(None, None, None, None, ("127.0.0.1", 443))],
    )
    with pytest.raises(SourceCollectionError, match="non-public"):
        fetch_public_source(url, approved_urls={url}, opener=FakeOpener(FakeResponse(b"ok", url=url, content_type="text/plain")))


def test_fetch_public_source_rejects_unapproved_redirect_target(public_dns):
    url = "https://docs.cdp.coinbase.com/x402/welcome"
    opener = FakeOpener(FakeResponse(b"content", url="https://127.0.0.1/private", content_type="text/plain"))
    with pytest.raises(SourceCollectionError, match="outside the approved"):
        fetch_public_source(url, approved_urls={url}, opener=opener)


def test_collect_assignment_sources_persists_hash_addressed_source_and_packet(tmp_path, public_dns):
    db_path = tmp_path / "ownera.sqlite3"
    _active_assignment(db_path, "Find SageKai Agent")
    url = "https://market.near.ai/agents"
    body = b"<html><head><title>Agent directory</title></head><body><main><p>Public agent directory listing.</p></main></body></html>"
    opener = FakeOpener(FakeResponse(body, url=url))
    result = collect_assignment_sources(db_path, "research-collector-1", opener=opener)
    assert result["sources_requested"] == 2
    assert result["sources_captured"] == 2
    assert result["execution_state"] == "SOURCE_COLLECTION_ONLY"
    from ownera.artifact_registry import SQLiteArtifactRegistry
    records = SQLiteArtifactRegistry(db_path).list_for_task(result["artifact_task_id"])
    assert {record.artifact_name for record in records} == {
        "source-01.json", "source-02.json", "SOURCE_COLLECTION.md"
    }
    packet = next(record for record in records if record.artifact_name == "SOURCE_COLLECTION.md")
    text = SQLiteArtifactRegistry(db_path).get(packet.sha256).decode()
    assert "not a completed research report" in text
    assert url in text and hashlib.sha256(body).hexdigest() in text


def test_collect_sources_requires_in_progress_assignment(tmp_path):
    db_path = tmp_path / "ownera.sqlite3"
    item = _active_assignment(
        db_path,
        "[internal research] Economics of micro-jobs on a marketplace with held payments and a judge",
    )
    item["assignment"]["status"] = "assigned"
    sync_assignments(db_path, assignments=[item])
    with pytest.raises(SourceCollectionError, match="in-progress"):
        collect_assignment_sources(db_path, "research-collector-1")


def test_collection_cycle_ignores_assignments_without_active_plans(tmp_path):
    db_path = tmp_path / "ownera.sqlite3"
    result = collect_active_assignment_sources(db_path)
    assert result["active_assignments"] == 0
    assert result["collections"] == []
    assert result["marketplace_actions"] == "none"


def test_collector_rejects_modified_plan_even_if_digest_field_is_unchanged(tmp_path):

    db_path = tmp_path / "ownera.sqlite3"
    _active_assignment(db_path, "Find SageKai Agent")
    with sqlite3.connect(db_path) as db:
        row = db.execute(
            "SELECT plan_json FROM near_market_assignment_plans WHERE assignment_id=?",
            ("research-collector-1",),
        ).fetchone()
        plan = json.loads(row[0])
        plan["source_urls_to_open"] = ["https://not-allowed.invalid/path"]
        db.execute(
            "UPDATE near_market_assignment_plans SET plan_json=? WHERE assignment_id=?",
            (json.dumps(plan), "research-collector-1"),
        )
    with pytest.raises(SourceCollectionError, match="does not match"):
        collect_assignment_sources(db_path, "research-collector-1")


def test_fetch_public_source_respects_robots_disallow(public_dns):
    url = "https://market.near.ai/agents"
    robots = FakeResponse(
        b"User-agent: *\nDisallow: /agents\n",
        content_type="text/plain",
        url="https://market.near.ai/robots.txt",
    )

    class SequenceOpener:
        def __init__(self):
            self.responses = [robots]
            self.calls = 0

        def open(self, request, timeout=0):
            self.calls += 1
            return self.responses.pop(0)

    opener = SequenceOpener()
    with pytest.raises(SourceCollectionError, match="robots.txt disallows"):
        fetch_public_source(url, approved_urls={url}, opener=opener)
    assert opener.calls == 1
