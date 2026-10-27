import sys
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from ownera.agent import MarketSnapshot
from ownera.external_provider import ExternalProviderError, SubprocessStrategyProvider
from ownera.investment import PortfolioSnapshot, Position


def _portfolio():
    return PortfolioSnapshot(
        "USD",
        Decimal("1000.00"),
        (Position("BTC", Decimal("0.01"), Decimal("60000")),),
    )


def _market():
    return MarketSnapshot(
        {"BTC": Decimal("60000.00")},
        datetime(2026, 10, 27, tzinfo=timezone.utc),
    )


def _provider(script, **kwargs):
    return SubprocessStrategyProvider(
        [sys.executable, "-c", script],
        timeout_seconds=kwargs.pop("timeout_seconds", 2),
        **kwargs,
    )


def test_subprocess_provider_sends_exact_decimal_strings_and_reads_proposal():
    script = (
        "import json,sys; "
        "p=json.load(sys.stdin); "
        "assert p['portfolio']['cash']=='1000.00'; "
        "assert p['portfolio']['positions'][0]['quantity']=='0.01'; "
        "print(json.dumps({'asset':'BTC','side':'BUY','quantity':'0.001',"
        "'price':'60000.00','currency':'USD'}))"
    )
    result = _provider(script).propose(_portfolio(), _market())

    assert result is not None
    assert result["quantity"] == "0.001"


def test_subprocess_provider_can_return_no_proposal():
    assert _provider("print('null')").propose(_portfolio(), _market()) is None


def test_subprocess_provider_rejects_non_json_output():
    with pytest.raises(ExternalProviderError, match="one JSON value"):
        _provider("print('not-json')").propose(_portfolio(), _market())


def test_subprocess_provider_rejects_non_object_output():
    with pytest.raises(ExternalProviderError, match="JSON object or null"):
        _provider("print('[]')").propose(_portfolio(), _market())


def test_subprocess_provider_rejects_nonzero_exit():
    with pytest.raises(ExternalProviderError, match="exited with status 3"):
        _provider("import sys; sys.exit(3)").propose(_portfolio(), _market())


def test_subprocess_provider_caps_stdout_while_reading():
    provider = _provider("import sys; sys.stdout.write('x' * 1000000)", max_output_bytes=1024)
    with pytest.raises(ExternalProviderError, match="size limit"):
        provider.propose(_portfolio(), _market())


def test_subprocess_provider_caps_stderr_while_reading():
    provider = _provider("import sys; sys.stderr.write('x' * 1000000)", max_output_bytes=1024)
    with pytest.raises(ExternalProviderError, match="size limit"):
        provider.propose(_portfolio(), _market())


def test_subprocess_provider_times_out():
    provider = _provider("import time; time.sleep(1)", timeout_seconds=0.05)
    with pytest.raises(ExternalProviderError, match="timed out"):
        provider.propose(_portfolio(), _market())


def test_subprocess_provider_requires_valid_configuration():
    with pytest.raises(ValueError, match="command"):
        SubprocessStrategyProvider([])
    with pytest.raises(ValueError, match="timeout"):
        SubprocessStrategyProvider(["provider"], timeout_seconds=0)
