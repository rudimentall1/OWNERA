"""JSON-lines-style subprocess bridge for untrusted strategy providers.

This boundary avoids importing third-party strategy code into OWNERA's process.
It is not an OS sandbox: production deployments must run the command in a
separately restricted container/user with no credentials and no execution tools.
"""

from __future__ import annotations

import json
import os
import subprocess
from collections.abc import Mapping, Sequence
from decimal import Decimal
from pathlib import Path
from typing import Any

from .agent import MarketSnapshot
from .investment import PortfolioSnapshot, Position


class ExternalProviderError(RuntimeError):
    """An external strategy process failed or violated its output protocol."""


class SubprocessStrategyProvider:
    """Call a proposal-only strategy command using a bounded JSON protocol.

    The provider receives only a normalized portfolio and market snapshot over
    stdin. Its stdout must contain exactly one JSON object or JSON null.
    Environment variables are explicitly allowlisted by the caller.
    """

    def __init__(
        self,
        command: Sequence[str],
        *,
        timeout_seconds: float = 10.0,
        working_directory: str | Path | None = None,
        environment: Mapping[str, str] | None = None,
        max_output_bytes: int = 64_000,
    ) -> None:
        if not command or any(not isinstance(part, str) or not part for part in command):
            raise ValueError("command must be a non-empty sequence of non-empty strings")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if max_output_bytes <= 0:
            raise ValueError("max_output_bytes must be positive")
        if environment and any(not isinstance(k, str) or not isinstance(v, str) for k, v in environment.items()):
            raise ValueError("environment keys and values must be strings")

        self.command = tuple(command)
        self.timeout_seconds = timeout_seconds
        self.working_directory = str(working_directory) if working_directory is not None else None
        self.environment = dict(environment or {})
        self.max_output_bytes = max_output_bytes

    @staticmethod
    def _payload(portfolio: PortfolioSnapshot, market: MarketSnapshot) -> dict[str, Any]:
        return {
            "protocol_version": 1,
            "portfolio": {
                "currency": portfolio.currency,
                "cash": format(portfolio.cash, "f"),
                "positions": [
                    {
                        "asset": position.asset,
                        "quantity": format(position.quantity, "f"),
                        "price": format(position.price, "f"),
                    }
                    for position in portfolio.positions
                ],
            },
            "market": {
                "observed_at": market.observed_at.isoformat(),
                "prices": {asset: format(price, "f") for asset, price in sorted(market.prices.items())},
            },
        }

    def propose(
        self,
        portfolio: PortfolioSnapshot,
        market: MarketSnapshot,
    ) -> Mapping[str, object] | None:
        request = json.dumps(
            self._payload(portfolio, market),
            sort_keys=True,
            separators=(",", ":"),
        )
        env = {
            "PATH": os.defpath,
            "PYTHONNOUSERSITE": "1",
            "PYTHONDONTWRITEBYTECODE": "1",
            **self.environment,
        }
        try:
            completed = subprocess.run(
                self.command,
                input=request,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=self.working_directory,
                env=env,
                timeout=self.timeout_seconds,
                check=False,
                shell=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise ExternalProviderError("strategy provider timed out") from exc
        except OSError as exc:
            raise ExternalProviderError("strategy provider could not be started") from exc

        if len(completed.stdout.encode("utf-8")) > self.max_output_bytes:
            raise ExternalProviderError("strategy provider output exceeded size limit")
        if completed.returncode != 0:
            detail = completed.stderr.strip()[:500]
            raise ExternalProviderError(
                f"strategy provider exited with status {completed.returncode}"
                + (f": {detail}" if detail else "")
            )
        try:
            result = json.loads(completed.stdout)
        except json.JSONDecodeError as exc:
            raise ExternalProviderError("strategy provider stdout must contain one JSON value") from exc
        if result is None:
            return None
        if not isinstance(result, dict):
            raise ExternalProviderError("strategy provider must return a JSON object or null")
        return result
