"""Validation boundary for proposals produced by external trading agents.

This adapter normalizes untrusted proposal data into OWNERA's domain model.
It does not make an untrusted provider safe to execute in-process: run third-party
agents in an isolated process/container with no credentials and no execution tools.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from decimal import Decimal, InvalidOperation
from typing import Protocol

from .agent import MarketSnapshot
from .investment import PortfolioSnapshot, TradeProposal, TradeSide


class StrategyAdapterError(ValueError):
    """An external strategy proposal failed OWNERA validation."""


class ProposalSource(Protocol):
    """Minimal proposal-only contract expected from a strategy provider."""

    def propose(
        self,
        portfolio: PortfolioSnapshot,
        market: MarketSnapshot,
    ) -> Mapping[str, object] | None: ...


def _exact_decimal(value: object, field: str) -> Decimal:
    if isinstance(value, (bool, float)):
        raise StrategyAdapterError(f"{field} must not be a float or boolean")
    if not isinstance(value, (str, int, Decimal)):
        raise StrategyAdapterError(f"{field} must be a decimal string, integer, or Decimal")
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise StrategyAdapterError(f"{field} is not a valid decimal") from exc
    if not parsed.is_finite():
        raise StrategyAdapterError(f"{field} must be finite")
    return parsed


class ValidatedStrategyAdapter:
    """Convert an external provider's proposal-only payload into a TradeProposal.

    Provider output is untrusted. OWNERA verifies its shape, allowed asset,
    currency, and price against the supplied market snapshot before the proposal
    can reach the investment firewall. This adapter is not a process sandbox.
    """

    _REQUIRED_FIELDS = frozenset({"asset", "side", "quantity", "price", "currency"})
    _OPTIONAL_FIELDS = frozenset({"rationale"})

    def __init__(
        self,
        provider: ProposalSource | Callable[
            [PortfolioSnapshot, MarketSnapshot], Mapping[str, object] | None
        ],
        *,
        allowed_assets: set[str] | frozenset[str],
        currency: str,
        provider_id: str,
    ) -> None:
        if not allowed_assets or any(not asset.strip() for asset in allowed_assets):
            raise ValueError("allowed_assets must contain non-empty asset symbols")
        if not currency.strip():
            raise ValueError("currency is required")
        if not provider_id.strip():
            raise ValueError("provider_id is required")
        self._provider = provider
        self.allowed_assets = frozenset(allowed_assets)
        self.currency = currency
        self.provider_id = provider_id

    def propose(
        self,
        portfolio: PortfolioSnapshot,
        market: MarketSnapshot,
    ) -> TradeProposal | None:
        if portfolio.currency != self.currency:
            raise StrategyAdapterError("portfolio currency does not match adapter currency")

        propose = getattr(self._provider, "propose", None)
        raw = (
            propose(portfolio, market)
            if callable(propose)
            else self._provider(portfolio, market)  # type: ignore[operator]
        )
        if raw is None:
            return None
        if not isinstance(raw, Mapping):
            raise StrategyAdapterError("provider must return a mapping or None")

        keys = frozenset(raw.keys())
        missing = self._REQUIRED_FIELDS - keys
        unknown = keys - self._REQUIRED_FIELDS - self._OPTIONAL_FIELDS
        if missing:
            raise StrategyAdapterError(f"proposal missing required fields: {', '.join(sorted(missing))}")
        if unknown:
            raise StrategyAdapterError(f"proposal contains unknown fields: {', '.join(sorted(map(str, unknown)))}")

        asset = raw["asset"]
        side = raw["side"]
        currency = raw["currency"]
        rationale = raw.get("rationale", f"proposal from {self.provider_id}")
        if not isinstance(asset, str) or not asset.strip():
            raise StrategyAdapterError("asset must be a non-empty string")
        if asset not in self.allowed_assets:
            raise StrategyAdapterError("asset is not allowed by OWNERA adapter configuration")
        if asset not in market.prices:
            raise StrategyAdapterError("asset is missing from the accepted market snapshot")
        if not isinstance(side, str):
            raise StrategyAdapterError("side must be a string")
        if not isinstance(currency, str) or currency != self.currency:
            raise StrategyAdapterError("proposal currency does not match adapter currency")
        if not isinstance(rationale, str) or len(rationale) > 500:
            raise StrategyAdapterError("rationale must be a string of at most 500 characters")

        try:
            trade_side = TradeSide(side)
        except ValueError as exc:
            raise StrategyAdapterError("side must be BUY or SELL") from exc

        quantity = _exact_decimal(raw["quantity"], "quantity")
        price = _exact_decimal(raw["price"], "price")
        if quantity <= 0:
            raise StrategyAdapterError("quantity must be positive")
        if price != market.price(asset):
            raise StrategyAdapterError("proposal price does not match accepted market snapshot")

        return TradeProposal(
            asset=asset,
            side=trade_side,
            quantity=quantity,
            price=price,
            currency=currency,
            rationale=rationale,
        )
