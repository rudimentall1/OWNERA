"""Bounded public-source capture for trusted NEAR research plans.

Only HTTPS URLs already present in OWNERA's deterministic plan are fetched.
Buyer text never supplies URLs, headers, credentials, commands, or instructions.
"""
from __future__ import annotations

import hashlib
import ipaddress
import json
import socket
import sqlite3
import time
import urllib.robotparser
from dataclasses import dataclass
from datetime import datetime, timezone
from html.parser import HTMLParser
from typing import ClassVar
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener

from ownera.artifact_registry import SQLiteArtifactRegistry

ALLOWED_SOURCE_HOSTS = frozenset({
    "docs.cdp.coinbase.com", "docs.virtuals.io", "olas.network",
    "docs.fetch.ai", "google.github.io", "docs.market.near.ai",
    "modelcontextprotocol.io", "www.zyte.com", "www.twilio.com",
    "replicate.com", "modal.com", "openrouter.ai", "www.deepl.com",
    "www.upwork.com", "www.fiverr.com", "openai.github.io",
    "platform.claude.com", "docs.langchain.com", "docs.crewai.com",
    "microsoft.github.io", "ai-sdk.dev", "docs.n8n.io",
    "registry.modelcontextprotocol.io", "smithery.ai", "glama.ai",
    "www.pulsemcp.com", "mcp.so", "developers.openai.com",
    "docs.anthropic.com", "huggingface.co", "www.npmjs.com", "pypi.org",
    "stripe.com", "www.rapidapi.com", "investors.etsy.com",
    "investors.upwork.com", "investors.airbnb.com", "amplitude.com",
    "mixpanel.com", "market.near.ai",
})
MAX_SOURCE_BYTES = 1_500_000
MAX_EXTRACTED_CHARS = 30_000
MAX_REDIRECTS = 3
USER_AGENT = "OWNERA-ResearchBot/0.1 (+https://github.com/rudimentall1/OWNERA)"


class SourceCollectionError(RuntimeError):
    """A public source could not be safely or reliably captured."""


@dataclass(frozen=True)
class CapturedSource:
    requested_url: str
    final_url: str
    fetched_at: str
    http_status: int
    content_type: str
    title: str
    text: str
    sha256: str
    byte_size: int
    redirect_count: int
    raw_content: bytes

    def to_dict(self) -> dict:
        return {
            "requested_url": self.requested_url,
            "final_url": self.final_url,
            "fetched_at": self.fetched_at,
            "http_status": self.http_status,
            "content_type": self.content_type,
            "title": self.title,
            "text": self.text,
            "sha256": self.sha256,
            "byte_size": self.byte_size,
            "redirect_count": self.redirect_count,
        }


class _TextExtractor(HTMLParser):
    _SKIP: ClassVar[frozenset[str]] = frozenset({"script", "style", "noscript", "svg", "canvas", "iframe", "nav", "footer", "header"})
    _BLOCK: ClassVar[frozenset[str]] = frozenset({"p", "div", "section", "article", "main", "h1", "h2", "h3", "h4", "li", "tr", "br"})

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.skip_depth = 0
        self.parts: list[str] = []
        self.title_parts: list[str] = []
        self.in_title = False

    def handle_starttag(self, tag: str, attrs) -> None:
        tag = tag.casefold()
        if tag in self._SKIP:
            self.skip_depth += 1
        if tag == "title":
            self.in_title = True
        if not self.skip_depth and tag in self._BLOCK:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        tag = tag.casefold()
        if tag == "title":
            self.in_title = False
        if tag in self._SKIP and self.skip_depth:
            self.skip_depth -= 1
        if not self.skip_depth and tag in self._BLOCK:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self.in_title:
            self.title_parts.append(data)
        if not self.skip_depth:
            cleaned = " ".join(data.split())
            if cleaned:
                self.parts.append(cleaned)

    def result(self) -> tuple[str, str]:
        lines = [" ".join(part.split()) for part in self.parts]
        text = "\n".join(line for line in lines if line)
        title = " ".join(" ".join(self.title_parts).split())
        return title[:500], text[:MAX_EXTRACTED_CHARS]


def _validate_public_host(host: str) -> None:
    if host not in ALLOWED_SOURCE_HOSTS:
        raise SourceCollectionError(f"source host is not allowlisted: {host}")
    try:
        infos = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    except OSError as exc:
        raise SourceCollectionError(f"DNS lookup failed for approved source host {host}") from exc
    addresses = {info[4][0] for info in infos}
    if not addresses:
        raise SourceCollectionError(f"approved source host has no resolved addresses: {host}")
    for address in addresses:
        ip = ipaddress.ip_address(address.split("%", 1)[0])
        if not ip.is_global:
            raise SourceCollectionError(f"approved source host resolved to a non-public address: {host}")


def _validate_url(url: str, approved_urls: set[str]) -> str:
    if url not in approved_urls:
        raise SourceCollectionError("requested URL is not present in the trusted assignment plan")
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise SourceCollectionError("source URL must be absolute HTTPS without embedded credentials")
    if parsed.port not in (None, 443):
        raise SourceCollectionError("source URL uses a non-standard HTTPS port")
    if parsed.fragment:
        url = url.split("#", 1)[0]
    _validate_public_host(parsed.hostname.casefold())
    return url


class _AllowlistedRedirectHandler(HTTPRedirectHandler):
    def __init__(self, approved_hosts: frozenset[str]):
        super().__init__()
        self.approved_hosts = approved_hosts
        self.redirect_count = 0

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        parsed = urlparse(newurl)
        if parsed.scheme != "https" or parsed.hostname not in self.approved_hosts:
            raise SourceCollectionError("redirect target is not an approved HTTPS source host")
        if parsed.username or parsed.password or parsed.port not in (None, 443):
            raise SourceCollectionError("redirect target contains unsafe URL components")
        self.redirect_count += 1
        if self.redirect_count > MAX_REDIRECTS:
            raise SourceCollectionError("source exceeded redirect limit")
        _validate_public_host(parsed.hostname)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _extract_payload(raw: bytes, content_type: str) -> tuple[str, str]:
    media_type = content_type.split(";", 1)[0].strip().casefold()
    decoded = raw.decode("utf-8", errors="replace")
    if media_type in {"application/json", "application/ld+json"} or media_type.endswith("+json"):
        try:
            parsed = json.loads(decoded)
        except json.JSONDecodeError as exc:
            raise SourceCollectionError("source declared JSON but returned invalid JSON") from exc
        text = json.dumps(parsed, ensure_ascii=False, indent=2, sort_keys=True)
        return "JSON source", text[:MAX_EXTRACTED_CHARS]
    if media_type in {"text/plain", "text/markdown", "text/xml", "application/xml"}:
        return "", "\n".join(line.strip() for line in decoded.splitlines() if line.strip())[:MAX_EXTRACTED_CHARS]
    if media_type in {"text/html", "application/xhtml+xml"}:
        parser = _TextExtractor()
        parser.feed(decoded)
        parser.close()
        return parser.result()
    raise SourceCollectionError(f"unsupported source content type: {media_type or 'missing'}")


def _check_robots(url: str, http_opener, cache: dict[str, urllib.robotparser.RobotFileParser]) -> None:
    parsed = urlparse(url)
    host = parsed.hostname
    if host not in cache:
        robots_url = f"https://{host}/robots.txt"
        request = Request(robots_url, headers={"User-Agent": USER_AGENT, "Accept": "text/plain"})
        parser = urllib.robotparser.RobotFileParser(robots_url)
        try:
            with http_opener.open(request, timeout=8) as response:
                raw = response.read(65_537)
                if len(raw) > 65_536:
                    raise SourceCollectionError("robots.txt exceeded the 64 KiB limit")
                parser.parse(raw.decode("utf-8", errors="replace").splitlines())
        except HTTPError as exc:
            if exc.code == 404:
                parser.parse([])
            else:
                raise SourceCollectionError(f"robots.txt returned HTTP {exc.code}") from exc
        except (URLError, TimeoutError, OSError) as exc:
            raise SourceCollectionError(f"robots.txt could not be checked for {host}") from exc
        cache[host] = parser
    if not cache[host].can_fetch("OWNERA-ResearchBot", url):
        raise SourceCollectionError("robots.txt disallows this source URL")


def fetch_public_source(
    url: str,
    *,
    approved_urls: set[str],
    opener=None,
    timeout: int = 15,
    robots_cache: dict[str, urllib.robotparser.RobotFileParser] | None = None,
) -> CapturedSource:
    safe_url = _validate_url(url, approved_urls)
    approved_hosts = frozenset(urlparse(item).hostname for item in approved_urls)
    redirect_handler = _AllowlistedRedirectHandler(approved_hosts)
    http_opener = opener or build_opener(redirect_handler)
    _check_robots(safe_url, http_opener, robots_cache if robots_cache is not None else {})
    request = Request(
        safe_url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/json,text/plain;q=0.9",
            "Accept-Encoding": "identity",
        },
    )
    try:
        with http_opener.open(request, timeout=timeout) as response:
            status = getattr(response, "status", 200)
            headers = response.headers
            content_type = headers.get("Content-Type", "")
            raw = response.read(MAX_SOURCE_BYTES + 1)
            final_url = response.geturl()
    except HTTPError as exc:
        raise SourceCollectionError(f"source returned HTTP {exc.code}") from exc
    except (URLError, TimeoutError, OSError) as exc:
        raise SourceCollectionError(f"source fetch failed: {type(exc).__name__}") from exc
    if status != 200:
        raise SourceCollectionError(f"source returned unexpected HTTP status {status}")
    if len(raw) > MAX_SOURCE_BYTES:
        raise SourceCollectionError("source exceeded the 1.5 MB capture limit")
    final = urlparse(final_url)
    if final.scheme != "https" or final.hostname not in approved_hosts or final.username or final.password:
        raise SourceCollectionError("final source URL is outside the approved HTTPS host set")
    title, text = _extract_payload(raw, content_type)
    if not text.strip():
        raise SourceCollectionError("source contained no extractable text")
    return CapturedSource(
        requested_url=safe_url,
        final_url=final_url,
        fetched_at=datetime.now(timezone.utc).isoformat(),
        http_status=status,
        content_type=content_type,
        title=title,
        text=text,
        sha256=hashlib.sha256(raw).hexdigest(),
        byte_size=len(raw),
        redirect_count=redirect_handler.redirect_count,
        raw_content=raw,
    )


def _task_identifier(assignment_id: str) -> str:
    return "nearresearch-" + hashlib.sha256(assignment_id.encode("utf-8")).hexdigest()[:32]


def collect_assignment_sources(database_path, assignment_id: str, *, opener=None, max_sources: int = 12) -> dict:
    """Capture trusted-plan sources for one in-progress assignment."""
    if not isinstance(assignment_id, str) or not assignment_id.strip() or len(assignment_id) > 255:
        raise ValueError("assignment_id must be a non-empty bounded string")
    if not 1 <= max_sources <= 12:
        raise ValueError("max_sources must be between 1 and 12")
    with sqlite3.connect(str(database_path), timeout=10) as db:
        row = db.execute(
            "SELECT plan_json,state FROM near_market_assignment_plans WHERE assignment_id=?",
            (assignment_id,),
        ).fetchone()
        assignment = db.execute(
            "SELECT status,payload_json FROM near_market_assignments WHERE assignment_id=?",
            (assignment_id,),
        ).fetchone()
    if row is None:
        raise SourceCollectionError("no trusted research plan exists for this assignment")
    if assignment is None or assignment[0].casefold() != "in_progress":
        raise SourceCollectionError("only in-progress assignments can collect research sources")
    if row[1] != "PLAN_READY_NOT_EXECUTABLE":
        raise SourceCollectionError("assignment research plan is not active")
    plan = json.loads(row[0])
    if plan.get("execution_state") != "PLAN_READY_NOT_EXECUTABLE":
        raise SourceCollectionError("research plan execution state is invalid")
    original_item = json.loads(assignment[1])
    from ownera.near_market_research_planner import build_assignment_plan
    rebuilt_plan = build_assignment_plan(original_item)
    if rebuilt_plan is None or rebuilt_plan != plan:
        raise SourceCollectionError("stored research plan does not match the original marketplace assignment")
    urls = plan.get("source_urls_to_open")
    if not isinstance(urls, list) or not urls or len(urls) > 12 or any(not isinstance(url, str) for url in urls):
        raise SourceCollectionError("trusted research plan contains an invalid source list")
    urls = urls[:max_sources]
    approved_urls = set(urls)

    registry = SQLiteArtifactRegistry(database_path)
    task_id = _task_identifier(assignment_id)
    worker_id = "near-market-source-collector"
    captured: list[CapturedSource] = []
    failures: list[dict] = []
    robots_cache: dict[str, urllib.robotparser.RobotFileParser] = {}
    existing_records: dict[str, list] = {}
    for record in registry.list_for_task(task_id):
        if record.worker_id == worker_id:
            existing_records.setdefault(record.artifact_name, []).append(record)
    for index, url in enumerate(urls, start=1):
        json_name = f"source-{index:02d}.json"
        raw_name = f"source-{index:02d}.raw"
        json_records = existing_records.get(json_name, [])
        raw_records = existing_records.get(raw_name, [])
        if json_records or raw_records:
            if len(json_records) != 1 or len(raw_records) != 1:
                failures.append({"url": url, "error": "Source artifact pair is incomplete; refusing to overwrite immutable evidence."})
                continue
            try:
                metadata = json.loads(registry.get(json_records[0].sha256).decode("utf-8"))
                source = metadata.get("source")
                raw = registry.get(raw_records[0].sha256)
                if (
                    metadata.get("assignment_id") != assignment_id
                    or metadata.get("plan_sha256") != plan["plan_sha256"]
                    or not isinstance(source, dict)
                    or source.get("requested_url") != url
                    or source.get("sha256") != hashlib.sha256(raw).hexdigest()
                    or source.get("byte_size") != len(raw)
                ):
                    raise SourceCollectionError("existing immutable source pair failed assignment, URL, or byte-integrity checks")
                captured.append(CapturedSource(**source, raw_content=raw))
                continue
            except (KeyError, TypeError, UnicodeDecodeError, json.JSONDecodeError, ValueError, OSError) as exc:
                failures.append({"url": url, "error": f"Existing source evidence is invalid: {type(exc).__name__}: {str(exc)[:180]}"})
                continue
        try:
            item = fetch_public_source(
                url, approved_urls=approved_urls, opener=opener, robots_cache=robots_cache
            )
            captured.append(item)
            artifact = {
                "schema": "ownera.near-research-source.v1",
                "assignment_id": assignment_id,
                "plan_sha256": plan["plan_sha256"],
                "source": item.to_dict(),
                "notice": "Captured public source text. Claims have not been independently reviewed.",
            }
            content = json.dumps(artifact, ensure_ascii=False, sort_keys=True, indent=2).encode("utf-8")
            registry.put(
                task_id=task_id,
                worker_id=worker_id,
                artifact_name=json_name,
                content=content,
                media_type="application/json",
            )
            registry.put(
                task_id=task_id,
                worker_id=worker_id,
                artifact_name=raw_name,
                content=item.raw_content,
                media_type=item.content_type.split(";", 1)[0] or "application/octet-stream",
            )
            time.sleep(0.25)
        except (SourceCollectionError, OSError, ValueError, sqlite3.Error) as exc:
            failures.append({"url": url, "error": f"{type(exc).__name__}: {str(exc)[:240]}"})

    packet_lines = [
        f"# Public-source collection: {plan['title']}",
        "",
        f"- Assignment: {assignment_id}",
        f"- Plan SHA-256: {plan['plan_sha256']}",
        f"- Captured through: {max(item.fetched_at for item in captured) if captured else 'none'}",
        f"- Sources successfully captured: {len(captured)} / {len(urls)}",
        "",
        "> This is a source packet, not a completed research report. No synthesis,",
        "> accuracy review, or independent semantic review has been performed.",
        "",
    ]
    for item in captured:
        packet_lines.extend([
            f"## {item.title or item.final_url}",
            "",
            f"- URL: {item.final_url}",
            f"- Captured: {item.fetched_at}",
            f"- HTTP: {item.http_status}",
            f"- Content-Type: {item.content_type}",
            f"- Raw-byte SHA-256: {item.sha256}",
            "",
            item.text[:5000],
            "",
        ])
    if failures:
        packet_lines.extend(["## Sources not captured", ""])
        packet_lines.extend(f"- {entry['url']}: {entry['error']}" for entry in failures)
        packet_lines.append("")
    packet_lines.extend([
        "## Research questions still requiring analysis",
        "",
        *[f"- {section}" for section in plan["deliverable_sections"]],
        "",
        "## Acceptance criteria",
        "",
        *[f"- {criterion}" for criterion in plan["acceptance_criteria"]],
        "",
    ])
    packet = "\n".join(packet_lines).encode("utf-8")
    registry.put(
        task_id=task_id,
        worker_id=worker_id,
        artifact_name="SOURCE_COLLECTION.md",
        content=packet,
        media_type="text/markdown",
    )
    return {
        "schema": "ownera.near-research-source-collection.v1",
        "assignment_id": assignment_id,
        "plan_sha256": plan["plan_sha256"],
        "sources_requested": len(urls),
        "sources_captured": len(captured),
        "sources_failed": failures,
        "artifact_task_id": task_id,
        "packet_sha256": hashlib.sha256(packet).hexdigest(),
        "execution_state": "SOURCE_COLLECTION_ONLY",
        "marketplace_actions": "none",
    }


def collect_active_assignment_sources(database_path, *, max_sources: int = 12) -> dict:
    """Poll the local assignment ledger and capture sources for active research plans."""
    with sqlite3.connect(str(database_path), timeout=10) as db:
        tables = {
            row[0] for row in db.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        if not {"near_market_assignment_plans", "near_market_assignments"}.issubset(tables):
            rows = []
        else:
            rows = db.execute(
                """SELECT p.assignment_id
                   FROM near_market_assignment_plans AS p
                   JOIN near_market_assignments AS a USING(assignment_id)
                   WHERE p.state='PLAN_READY_NOT_EXECUTABLE'
                     AND lower(a.status)='in_progress'
                   ORDER BY a.last_seen_at, p.assignment_id"""
            ).fetchall()
    completed = []
    failures = []
    for (assignment_id,) in rows:
        try:
            completed.append(collect_assignment_sources(
                database_path, assignment_id, max_sources=max_sources
            ))
        except (SourceCollectionError, OSError, ValueError, sqlite3.Error) as exc:
            failures.append({
                "assignment_id": assignment_id,
                "error": f"{type(exc).__name__}: {str(exc)[:240]}",
            })
    return {
        "schema": "ownera.near-research-source-collector-cycle.v1",
        "active_assignments": len(rows),
        "collections": completed,
        "failures": failures,
        "marketplace_actions": "none",
    }
