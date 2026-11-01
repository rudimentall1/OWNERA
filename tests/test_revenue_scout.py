import json

import pytest

from ownera.revenue_scout import LocalOllamaRevenueScout, RevenueScoutError


def _candidate(**overrides):
    value = {
        "source_name": "Kwork",
        "source_url": "https://kwork.ru/projects/3270680/view",
        "source_status": "OPEN",
        "source_checked_at": "2026-11-01T11:00:00+05:00",
        "status_evidence": "Original public page shows that the project accepts responses.",
        "title": "Install an existing Telegram bot on a server",
        "description": "An existing aiogram bot should be deployed and its response delays investigated.",
        "budget_min": "2000",
        "budget_max": "6000",
        "currency": "RUB",
    }
    value.update(overrides)
    return value


def _model_result(**overrides):
    value = {
        "request_type": "BUYER_REQUEST",
        "fit_score": 88,
        "required_capabilities": ["Python", "Linux", "aiogram", "systemd"],
        "deliverables": ["Deploy the supplied bot", "Investigate response delays"],
        "missing_information": ["Server access method", "Reproduction steps for slowdowns"],
        "risk_flags": [],
        "estimated_effort_hours": 3.0,
        "recommendation": "REVIEW",
        "rationale": "A bounded deployment and diagnosis task matches existing Python and Linux work.",
    }
    value.update(overrides)
    return value


class _FakeResponse:
    status = 200

    def __init__(self, content):
        self._body = json.dumps({"message": {"content": json.dumps(content)}}).encode()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return self._body


def test_scout_uses_local_loopback_and_preserves_verified_status(monkeypatch):
    import urllib.request

    seen = {}

    def fake_urlopen(request, timeout):
        seen["url"] = request.full_url
        seen["timeout"] = timeout
        seen["body"] = json.loads(request.data)
        return _FakeResponse(_model_result())

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    result = LocalOllamaRevenueScout(timeout_seconds=12).qualify(_candidate())
    assert result.request_type == "BUYER_REQUEST"
    assert result.action_status == "OWNER_REVIEW_REQUIRED"
    assert result.source_status == "OPEN"
    assert result.budget_max == "6000"
    assert seen["url"] == "http://127.0.0.1:11434/api/chat"
    assert seen["timeout"] == 12
    assert seen["body"]["options"]["num_thread"] == 2
    assert seen["body"]["format"]["additionalProperties"] is False


def test_scout_never_turns_closed_or_unknown_source_into_actionable_lead(monkeypatch):
    import urllib.request

    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: _FakeResponse(_model_result()))
    scout = LocalOllamaRevenueScout()
    closed = scout.qualify(_candidate(source_status="CLOSED"))
    unknown = scout.qualify(_candidate(source_status="UNKNOWN"))
    assert closed.action_status == "NOT_ACTIONABLE_SOURCE_NOT_VERIFIED_OPEN"
    assert unknown.action_status == "NOT_ACTIONABLE_SOURCE_NOT_VERIFIED_OPEN"


def test_scout_rejects_seller_portfolio_and_risk_flag_even_if_model_score_is_high(monkeypatch):
    import urllib.request

    monkeypatch.setattr(
        urllib.request, "urlopen",
        lambda *a, **k: _FakeResponse(_model_result(request_type="SELLER_OFFER")),
    )
    result = LocalOllamaRevenueScout().qualify(_candidate())
    assert result.action_status == "NOT_ACTIONABLE_NOT_A_BUYER_REQUEST"


def test_scout_rejects_external_provider_urls():
    with pytest.raises(RevenueScoutError, match="loopback"):
        LocalOllamaRevenueScout(base_url="https://example.com")


def test_scout_requires_evidence_for_open_status():
    with pytest.raises(RevenueScoutError, match="explicit evidence"):
        LocalOllamaRevenueScout().qualify(_candidate(status_evidence="open"))


def test_scout_rejects_malformed_model_output(monkeypatch):
    import urllib.request

    monkeypatch.setattr(
        urllib.request, "urlopen",
        lambda *a, **k: _FakeResponse(_model_result(unknown_extra="not allowed")),
    )
    with pytest.raises(RevenueScoutError, match="required result fields"):
        LocalOllamaRevenueScout().qualify(_candidate())
