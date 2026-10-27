"""JSON-lines-style subprocess bridge for untrusted strategy providers.

This boundary avoids importing third-party strategy code into OWNERA's process.
It is not an OS sandbox: production deployments must run the command in a
separately restricted container/user with no credentials and no execution tools.
"""

from __future__ import annotations

import json
import os
import subprocess
import threading
import time
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from .agent import MarketSnapshot
from .investment import PortfolioSnapshot


class ExternalProviderError(RuntimeError):
    """An external strategy process failed or violated its output protocol."""


class SubprocessStrategyProvider:
    """Call a proposal-only strategy command using a bounded JSON protocol.

    The provider receives only a normalized portfolio and market snapshot over
    stdin. Its stdout must contain exactly one JSON object or JSON null.
    Environment variables are explicitly allowlisted by the caller. Both output
    streams are byte-capped while being read, not after buffering in memory.
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
        ).encode("utf-8")
        env = {
            "PATH": os.defpath,
            "PYTHONNOUSERSITE": "1",
            "PYTHONDONTWRITEBYTECODE": "1",
            **self.environment,
        }
        try:
            process = subprocess.Popen(
                self.command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=self.working_directory,
                env=env,
                shell=False,
            )
        except OSError as exc:
            raise ExternalProviderError("strategy provider could not be started") from exc

        stdout = bytearray()
        stderr = bytearray()
        output_lock = threading.Lock()
        output_size = 0
        output_exceeded = threading.Event()

        def drain(stream: Any, destination: bytearray) -> None:
            nonlocal output_size
            try:
                while True:
                    chunk = stream.read(4096)
                    if not chunk:
                        return
                    with output_lock:
                        remaining = self.max_output_bytes - output_size
                        output_size += len(chunk)
                        if remaining > 0:
                            destination.extend(chunk[:remaining])
                        if output_size > self.max_output_bytes:
                            output_exceeded.set()
                            try:
                                process.kill()
                            except OSError:
                                pass
                            return
            finally:
                stream.close()

        def send_input() -> None:
            assert process.stdin is not None
            try:
                process.stdin.write(request)
                process.stdin.flush()
            except (BrokenPipeError, OSError):
                pass
            finally:
                process.stdin.close()

        assert process.stdout is not None and process.stderr is not None
        readers = [
            threading.Thread(target=drain, args=(process.stdout, stdout), daemon=True),
            threading.Thread(target=drain, args=(process.stderr, stderr), daemon=True),
        ]
        writer = threading.Thread(target=send_input, daemon=True)
        for thread in readers:
            thread.start()
        writer.start()

        deadline = time.monotonic() + self.timeout_seconds
        try:
            while process.poll() is None:
                if output_exceeded.is_set():
                    break
                if time.monotonic() >= deadline:
                    process.kill()
                    process.wait()
                    raise ExternalProviderError("strategy provider timed out")
                time.sleep(0.005)
            process.wait()
        finally:
            if process.poll() is None:
                process.kill()
                process.wait()
            writer.join(timeout=0.2)
            for thread in readers:
                thread.join(timeout=0.2)

        if output_exceeded.is_set():
            raise ExternalProviderError("strategy provider output exceeded size limit")
        if process.returncode != 0:
            detail = stderr.decode("utf-8", errors="replace").strip()[:500]
            raise ExternalProviderError(
                f"strategy provider exited with status {process.returncode}"
                + (f": {detail}" if detail else "")
            )
        try:
            result = json.loads(stdout.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise ExternalProviderError("strategy provider stdout must contain one JSON value") from exc
        if result is None:
            return None
        if not isinstance(result, dict):
            raise ExternalProviderError("strategy provider must return a JSON object or null")
        return result
