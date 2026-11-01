import json
from datetime import datetime, timezone

import pytest

from ownera.evidence_registry import EvidenceStatus, SQLiteOpportunityEvidenceRegistry
from ownera.sources.openradar import OpenRadarPublicFeedAdapter, OpenRadarSourceError


def _record(**changes):
    row = {
        "id": "6d23b3b2-1d49-4f5f-8cf8-98f694ea4637",
        "type": "gig",
        "title": "Нужен разработчик Python для Telegram-бота",
        "text": "Ищу исполнителя: нужно развернуть существующего aiogram Telegram-бота на Ubuntu, проверить systemd и исправить запуск после перезагрузки. Бюджет обсуждаем.",
        "url": "https://kwork.ru/projects/3270680/view",
        "canonicalUrl": "https://kwork.ru/projects/3270680/view",
        "score": 74,
        "currency": "RUB",
        "paymentPeriod": "fixed",
        "skills": ["Python", "Telegram", "Linux"],
        "publishedAt": "2026-10-31T12:00:00.000Z",
        "createdAt": "2026-10-31T12:01:00.000Z",
        "contacts": ["must-not-be-captured"],
        "sourceRef": {"platform": "kwork", "visibility": "public"},
    }
    row.update(changes)
    return row


def _payload(*rows):
    return ("\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n").encode()


@pytest.fixture
def registry(tmp_path):
    class NoOwner:
        def authenticate(self, credential):
            raise PermissionError("manual review auth not configured")
    return SQLiteOpportunityEvidenceRegistry(tmp_path / "evidence.db", NoOwner())


def test_openradar_ingest_marks_feed_sighting_observed_not_active(registry):
    adapter = OpenRadarPublicFeedAdapter(registry)
    item = adapter.ingest(
        _payload(_record()), now=datetime(2026, 11, 1, tzinfo=timezone.utc)
    )[0]
    assert item.source_status == "UNKNOWN"
    assert item.lifecycle_status == "OBSERVED"
    assert item.buyer_intent == "BUYER_REQUEST_SIGNAL"
    assert item.relevance_score > 0
    evidence = registry.get(item.evidence_id)
    assert evidence.status is EvidenceStatus.PENDING
    assert registry.source_observation(f"openradar:{item.gig_id}")["lifecycle_status"] == "OBSERVED"
    assert registry.verify(item.evidence_id)
    assert "must-not-be-captured" not in evidence.content_snapshot
    assert '"contacts_available":false' in evidence.content_snapshot


def test_openradar_repeat_feed_is_idempotent(registry):
    adapter = OpenRadarPublicFeedAdapter(registry)
    now = datetime(2026, 11, 1, tzinfo=timezone.utc)
    first = adapter.ingest(_payload(_record()), now=now)[0]
    second = adapter.ingest(
        _payload(_record()), now=datetime(2026, 11, 1, 1, tzinfo=timezone.utc)
    )[0]
    assert first.gig_id == second.gig_id
    assert first.evidence_id == second.evidence_id
    assert registry.verify(first.evidence_id)


def test_openradar_content_change_creates_new_pending_evidence(registry):
    adapter = OpenRadarPublicFeedAdapter(registry)
    first = adapter.ingest(_payload(_record()))[0]
    second = adapter.ingest(_payload(_record(text="Ищу Python-разработчика для интеграции REST API.")))[0]
    assert first.gig_id == second.gig_id
    assert first.evidence_id != second.evidence_id
    assert registry.verify(first.evidence_id)
    assert registry.verify(second.evidence_id)


def test_openradar_deduplicates_repeated_ids_in_one_feed(registry):
    items = OpenRadarPublicFeedAdapter(registry).ingest(_payload(_record(), _record()))
    assert len(items) == 1


def test_openradar_rejects_non_gig_and_invalid_urls(registry):
    adapter = OpenRadarPublicFeedAdapter(registry)
    with pytest.raises(OpenRadarSourceError, match="non-gig"):
        adapter.ingest(_payload(_record(type="job")))
    with pytest.raises(OpenRadarSourceError, match="HTTPS"):
        adapter.ingest(_payload(_record(url="http://kwork.ru/project/1")))


def test_openradar_rejects_bad_payload_dates_and_budget(registry):
    adapter = OpenRadarPublicFeedAdapter(registry)
    with pytest.raises(OpenRadarSourceError, match="publishedAt"):
        adapter.ingest(_payload(_record(publishedAt="yesterday")))
    with pytest.raises(OpenRadarSourceError, match="budget"):
        adapter.ingest(_payload(_record(budget=-1)))


def test_openradar_rejects_malformed_ndjson_and_over_limit(registry):
    adapter = OpenRadarPublicFeedAdapter(registry)
    with pytest.raises(OpenRadarSourceError, match="malformed"):
        adapter.ingest(b"{bad json}\n")
    with pytest.raises(ValueError, match="between 1 and 200"):
        adapter.fetch_payload(limit=201)


def test_openradar_downgrades_employment_and_seller_ads():
    from ownera.sources.openradar import _relevance

    vacancy_score, vacancy_reasons = _relevance(
        "Ищу помощника на удалённую подработку, 1-2 часа в день",
        "Гибкий график работы", ("Telegram",),
    )
    seller_score, seller_reasons = _relevance(
        "Предлагаю услуги по разработке Telegram-ботов",
        "Портфолио и цены по запросу", ("Python",),
    )
    assert vacancy_score <= 20
    assert "employment_or_vacancy_language" in vacancy_reasons
    assert seller_score <= 20
    assert "seller_offer_or_promotion_language" in seller_reasons
