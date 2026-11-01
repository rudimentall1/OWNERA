"""Read-only guest-feed adapter for OpenRadar gig listings.

The guest feed is delayed and does not provide buyer contacts. A feed sighting
is therefore OBSERVED evidence, never proof that a job remains open or actionable.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen
from uuid import NAMESPACE_URL, UUID, uuid5

OPENRADAR_FEED_URL = "https://openradar.fun/v2/feed"


class OpenRadarSourceError(RuntimeError):
    """The public OpenRadar feed could not be safely fetched or parsed."""


@dataclass(frozen=True)
class DiscoveredGig:
    gig_id: UUID
    evidence_id: UUID
    title: str
    text: str
    source_url: str
    canonical_url: str
    published_at: datetime
    created_at: datetime
    budget: Decimal | None
    currency: str | None
    payment_period: str | None
    skills: tuple[str, ...]
    source_platform: str | None
    feed_score: int | None
    relevance_score: int
    relevance_reasons: tuple[str, ...]
    buyer_intent: str
    source_status: str
    lifecycle_status: str
    contacts_available: bool

    def to_dict(self) -> dict:
        return {
            "gig_id": str(self.gig_id),
            "evidence_id": str(self.evidence_id),
            "title": self.title,
            "text_excerpt": self.text[:700],
            "source_url": self.source_url,
            "canonical_url": self.canonical_url,
            "published_at": self.published_at.isoformat(),
            "created_at": self.created_at.isoformat(),
            "budget": str(self.budget) if self.budget is not None else None,
            "currency": self.currency,
            "payment_period": self.payment_period,
            "skills": list(self.skills),
            "source_platform": self.source_platform,
            "feed_score": self.feed_score,
            "relevance_score": self.relevance_score,
            "relevance_reasons": list(self.relevance_reasons),
            "buyer_intent": self.buyer_intent,
            "source_status": self.source_status,
            "lifecycle_status": self.lifecycle_status,
            "contacts_available": self.contacts_available,
        }


_CAPABILITY_PATTERNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("python_backend", ("python", "fastapi", "django", "flask", "скрипт", "скрипты")),
    ("telegram_bots", ("telegram", "телеграм", "telegram bot", "бот", "aiogram")),
    ("deployment_automation", ("docker", "linux", "ubuntu", "сервер", "deploy", "deployment", "развернуть", "настроить", "systemd")),
    ("web3_security", ("web3", "blockchain", "solidity", "smart contract", "смарт-контракт", "аудит", "audit", "defi")),
    ("api_integrations", ("api", "интеграция", "интеграции", "webhook", "автоматизац", "automation", "бот", "crm")),
    ("parsing_data", ("парсер", "парсинг", "parser", "scraping", "сбор данных", "data extraction")),
)
_BUYER_PATTERNS = (
    "ищу исполнителя", "ищу разработчика", "ищу python-разработчика",
    "нужен разработчик", "нужна разработка", "нужно разработать",
    "нужно создать", "нужно настроить", "необходимо разработать",
    "задача:", "заказ:", "заказать", "создать", "разработать", "сделать",
    "развернуть", "настроить", "интегрировать", "исправить", "доработать",
    "подключить", "реализовать", "собрать бот", "собрать бота",
    "парсер", "разработка чат-бота", "бот для бизнеса", "аудит сайта",
)
_EMPLOYMENT_PATTERNS = (
    "подработка", "вакансия", "ищу помощника", "ищу ассистента",
    "ищу менеджера", "ищем сотрудника", "в команду", "на постоянную работу",
    "график работы", "рабочий график", "оклад", "зарплата", "заработная плата",
    "оплата за смену", "сменный график", "1-2 часа в день", "2-3 часа в день",
)
_SELLER_PATTERNS = (
    "предлагаю услуги", "оказываю услуги", "готов выполнить", "выполню заказ",
    "мои услуги", "портфолио", "закажите у меня", "скидка", "акция", "продаю",
    "набор клиентов", "рекламное предложение", "делаю сайты на заказ",
)


def _parse_time(value: object, field: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise OpenRadarSourceError(f"gig has invalid {field}")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise OpenRadarSourceError(f"gig has invalid {field}") from exc
    if parsed.tzinfo is None:
        raise OpenRadarSourceError(f"gig {field} must include a timezone")
    return parsed.astimezone(timezone.utc)


def _safe_source_url(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > 2048:
        raise OpenRadarSourceError(f"gig has invalid {field}")
    parsed = urlparse(value)
    if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password:
        raise OpenRadarSourceError(f"gig {field} must be an absolute HTTPS URL without credentials")
    return value


def _budget(value: object) -> Decimal | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        raise OpenRadarSourceError("gig has invalid budget")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise OpenRadarSourceError("gig has invalid budget") from exc
    if not result.is_finite() or result < 0:
        raise OpenRadarSourceError("gig has invalid budget")
    return result


def _buyer_intent(title: str, text: str) -> str:
    content = f"{title}\n{text}".casefold()
    if any(pattern in content for pattern in _SELLER_PATTERNS):
        return "SELLER_OR_PROMOTION"
    if any(pattern in content for pattern in _EMPLOYMENT_PATTERNS) and not any(
        pattern in content for pattern in _BUYER_PATTERNS
    ):
        return "EMPLOYMENT_OR_VACANCY"
    if any(pattern in content for pattern in _BUYER_PATTERNS):
        return "BUYER_REQUEST_SIGNAL"
    return "UNKNOWN"


def _relevance(title: str, text: str, skills: tuple[str, ...]) -> tuple[int, tuple[str, ...]]:
    content = f"{title}\n{text}\n{' '.join(skills)}".casefold()
    matched: list[str] = []
    for category, patterns in _CAPABILITY_PATTERNS:
        if any(pattern in content for pattern in patterns):
            matched.append(category)
    buyer = _buyer_intent(title, text)
    score = min(100, len(matched) * 18 + (24 if buyer == "BUYER_REQUEST_SIGNAL" else 0))
    if buyer in {"SELLER_OR_PROMOTION", "EMPLOYMENT_OR_VACANCY"}:
        score = min(score, 20)
    elif buyer == "UNKNOWN":
        score = min(score, 40)
    reasons = [f"capability_match:{item}" for item in matched]
    if buyer == "BUYER_REQUEST_SIGNAL":
        reasons.append("buyer_intent_language_match")
    elif buyer == "SELLER_OR_PROMOTION":
        reasons.append("seller_offer_or_promotion_language")
    elif buyer == "EMPLOYMENT_OR_VACANCY":
        reasons.append("employment_or_vacancy_language")
    return score, tuple(reasons)


class OpenRadarPublicFeedAdapter:
    """Read public gig records and capture them as non-actionable OBSERVED evidence."""

    MAX_LIMIT = 200
    MAX_RESPONSE_BYTES = 10 * 1024 * 1024
    MAX_RECORDS = 200
    TIMEOUT_SECONDS = 15
    SOURCE_NAME = "OpenRadar public guest feed"
    FEED_DELAY_HOURS = 12

    def __init__(self, evidence_registry: object) -> None:
        capture = getattr(evidence_registry, "capture_source_observation", None)
        if not callable(capture):
            raise TypeError("evidence_registry must provide capture_source_observation")
        self._registry = evidence_registry

    def fetch_payload(self, *, limit: int = 100) -> bytes:
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= self.MAX_LIMIT:
            raise ValueError(f"limit must be between 1 and {self.MAX_LIMIT}")
        query = urlencode({"limit": limit, "type": "gig", "format": "ndjson"})
        url = f"{OPENRADAR_FEED_URL}?{query}"
        request = Request(
            url,
            headers={
                "Accept": "application/x-ndjson",
                "User-Agent": "OWNERA-public-opportunity-intake/0.1",
            },
            method="GET",
        )
        try:
            with urlopen(request, timeout=self.TIMEOUT_SECONDS) as response:
                final = urlparse(response.geturl())
                if final.scheme != "https" or final.hostname not in {"openradar.fun", "www.openradar.fun"}:
                    raise OpenRadarSourceError("OpenRadar feed redirected outside its domain")
                content_type = response.headers.get("Content-Type", "").lower()
                if "application/x-ndjson" not in content_type and "application/json" not in content_type:
                    raise OpenRadarSourceError("OpenRadar did not return an NDJSON/JSON feed")
                payload = response.read(self.MAX_RESPONSE_BYTES + 1)
        except HTTPError as exc:
            raise OpenRadarSourceError(f"OpenRadar returned HTTP {exc.code}") from exc
        except URLError as exc:
            raise OpenRadarSourceError("OpenRadar feed request failed") from exc
        if len(payload) > self.MAX_RESPONSE_BYTES:
            raise OpenRadarSourceError("OpenRadar feed exceeds size limit")
        return payload

    @staticmethod
    def _record(raw: object) -> dict:
        if not isinstance(raw, dict):
            raise OpenRadarSourceError("OpenRadar feed contains a non-object record")
        required = ("id", "type", "title", "text", "url", "publishedAt", "createdAt")
        if any(name not in raw for name in required):
            raise OpenRadarSourceError("OpenRadar record is missing required fields")
        if raw["type"] != "gig":
            raise OpenRadarSourceError("OpenRadar endpoint returned a non-gig record")
        try:
            gig_id = UUID(str(raw["id"]))
        except ValueError as exc:
            raise OpenRadarSourceError("OpenRadar record has invalid UUID") from exc
        title, text = raw["title"], raw["text"]
        if not isinstance(title, str) or not title.strip() or len(title) > 1200:
            raise OpenRadarSourceError("OpenRadar record has invalid title")
        if not isinstance(text, str) or not text.strip() or len(text) > 100_000:
            raise OpenRadarSourceError("OpenRadar record has invalid text")
        source_url = _safe_source_url(raw["url"], "url")
        canonical = _safe_source_url(raw.get("canonicalUrl", source_url), "canonicalUrl")
        skills_raw = raw.get("skills") or []
        if not isinstance(skills_raw, list) or len(skills_raw) > 100 or any(
            not isinstance(x, str) or not x.strip() or len(x) > 100 for x in skills_raw
        ):
            raise OpenRadarSourceError("OpenRadar record has invalid skills")
        currency = raw.get("currency")
        if currency is not None and (
            not isinstance(currency, str) or len(currency) != 3 or not currency.isalpha()
        ):
            raise OpenRadarSourceError("OpenRadar record has invalid currency")
        period = raw.get("paymentPeriod")
        if period is not None and (not isinstance(period, str) or len(period) > 40):
            raise OpenRadarSourceError("OpenRadar record has invalid paymentPeriod")
        feed_score = raw.get("score")
        if feed_score is not None and (
            isinstance(feed_score, bool) or not isinstance(feed_score, int) or not 0 <= feed_score <= 100
        ):
            raise OpenRadarSourceError("OpenRadar record has invalid feed score")
        source_ref = raw.get("sourceRef")
        if source_ref is not None and not isinstance(source_ref, dict):
            raise OpenRadarSourceError("OpenRadar record has invalid sourceRef")
        return {
            "gig_id": gig_id,
            "title": title.strip(),
            "text": text.strip(),
            "source_url": source_url,
            "canonical_url": canonical,
            "published_at": _parse_time(raw["publishedAt"], "publishedAt"),
            "created_at": _parse_time(raw["createdAt"], "createdAt"),
            "budget": _budget(raw.get("budget")),
            "currency": currency.upper() if currency else None,
            "payment_period": period,
            "skills": tuple(skills_raw),
            "source_ref": source_ref,
            "feed_score": feed_score,
            "raw": raw,
        }

    def ingest(
        self, payload: bytes, *, now: datetime | None = None
    ) -> tuple[DiscoveredGig, ...]:
        if not isinstance(payload, bytes) or len(payload) > self.MAX_RESPONSE_BYTES:
            raise OpenRadarSourceError("OpenRadar payload is invalid or exceeds size limit")
        observed_at = now or datetime.now(timezone.utc)
        if observed_at.tzinfo is None:
            raise ValueError("now must be timezone-aware")
        observed_at = observed_at.astimezone(timezone.utc)
        try:
            lines = [line for line in payload.decode("utf-8").splitlines() if line.strip()]
        except UnicodeDecodeError as exc:
            raise OpenRadarSourceError("OpenRadar feed is not UTF-8") from exc
        if len(lines) > self.MAX_RECORDS:
            raise OpenRadarSourceError("OpenRadar feed contains too many records")
        records: list[dict] = []
        seen: set[UUID] = set()
        for line in lines:
            try:
                raw = json.loads(line)
            except json.JSONDecodeError as exc:
                raise OpenRadarSourceError("OpenRadar feed contains malformed NDJSON") from exc
            item = self._record(raw)
            if item["gig_id"] in seen:
                continue
            seen.add(item["gig_id"])
            records.append(item)

        results: list[DiscoveredGig] = []
        for item in records:
            safe_source_ref = item["source_ref"] or {}
            snapshot_data = {
                "source": OPENRADAR_FEED_URL,
                "feed_delay_hours": self.FEED_DELAY_HOURS,
                "contacts_available": False,
                "source_status": "UNKNOWN",
                "feed_observed_at": observed_at.isoformat(),
                "gig_id": str(item["gig_id"]),
                "type": "gig",
                "title": item["title"],
                "text": item["text"][:8_000],
                "source_url": item["source_url"],
                "canonical_url": item["canonical_url"],
                "published_at": item["published_at"].isoformat(),
                "created_at": item["created_at"].isoformat(),
                "budget": str(item["budget"]) if item["budget"] is not None else None,
                "currency": item["currency"],
                "payment_period": item["payment_period"],
                "skills": list(item["skills"]),
                "source_platform": str(safe_source_ref.get("platform", ""))[:80],
                "feed_score": item["feed_score"],
            }
            snapshot = json.dumps(
                snapshot_data, sort_keys=True, separators=(",", ":"),
                ensure_ascii=False, allow_nan=False,
            )
            if len(snapshot) > 16_384:
                raise OpenRadarSourceError("bounded OpenRadar evidence snapshot is too large")
            semantic = dict(snapshot_data)
            semantic.pop("feed_observed_at", None)
            fingerprint = hashlib.sha256(json.dumps(
                semantic, sort_keys=True, separators=(",", ":"),
                ensure_ascii=False, allow_nan=False,
            ).encode()).hexdigest()
            opportunity_id = uuid5(NAMESPACE_URL, f"openradar:{item['gig_id']}")
            evidence = self._registry.capture_source_observation(
                source_key=f"openradar:{item['gig_id']}",
                opportunity_id=opportunity_id,
                semantic_fingerprint=fingerprint,
                source_name=self.SOURCE_NAME,
                source_url=item["source_url"],
                content_snapshot=snapshot,
                lifecycle_status="OBSERVED",
                observed_at=observed_at,
            )
            score, reasons = _relevance(item["title"], item["text"], item["skills"])
            buyer_intent = _buyer_intent(item["title"], item["text"])
            results.append(DiscoveredGig(
                gig_id=item["gig_id"], evidence_id=evidence.evidence_id,
                title=item["title"], text=item["text"], source_url=item["source_url"],
                canonical_url=item["canonical_url"], published_at=item["published_at"],
                created_at=item["created_at"], budget=item["budget"],
                currency=item["currency"], payment_period=item["payment_period"],
                skills=item["skills"],
                source_platform=str(safe_source_ref.get("platform")) if safe_source_ref.get("platform") else None,
                feed_score=item["feed_score"], relevance_score=score,
                relevance_reasons=reasons, buyer_intent=buyer_intent,
                source_status="UNKNOWN", lifecycle_status="OBSERVED", contacts_available=False,
            ))
        return tuple(results)

    def discover(self, *, limit: int = 100) -> tuple[DiscoveredGig, ...]:
        return self.ingest(self.fetch_payload(limit=limit))
