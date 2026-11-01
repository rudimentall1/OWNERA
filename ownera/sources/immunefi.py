"""Read-only intake adapter for Immunefi's public bounty catalog.

The endpoint is public but does not publish a stable formal API contract. This
adapter validates the observed schema, fails closed on structural drift, and
never submits reports or authorizes testing.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
import json
import typing
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen
from uuid import UUID, uuid4


IMMUNEFI_CATALOG_URL = "https://immunefi.com/public-api/bounties.json"


class SourceAdapterError(RuntimeError):
    """A public source could not be safely fetched or parsed."""


class EvidenceCapturePort(typing.Protocol):
    def capture(
        self,
        *,
        opportunity_id: UUID,
        source_name: str,
        source_url: str,
        content_snapshot: str,
    ):
        ...


@dataclass(frozen=True)
class DiscoveredBounty:
    """Unqualified public listing. max_bounty_usd is a ceiling, never guaranteed revenue."""

    opportunity_id: UUID
    evidence_id: UUID
    project: str
    slug: str
    source_url: str
    max_bounty_ceiling: Decimal | None
    program_types: tuple[str, ...]
    project_types: tuple[str, ...]
    ecosystems: tuple[str, ...]
    languages: tuple[str, ...]
    kyc_required: bool
    invite_only: bool
    launch_date: datetime
    end_date: datetime | None
    assets_count: int
    captured_at: datetime


class ImmunefiPublicCatalogAdapter:
    """Fetch active public Immunefi listings and store bounded owner-review evidence."""

    MAX_RESPONSE_BYTES = 12 * 1024 * 1024
    MAX_CANDIDATES = 5_000
    TIMEOUT_SECONDS = 20
    SOURCE_NAME = "Immunefi public bounty catalog"

    def __init__(self, evidence_registry: EvidenceCapturePort) -> None:
        self._evidence_registry = evidence_registry

    def fetch_payload(self) -> bytes:
        request = Request(
            IMMUNEFI_CATALOG_URL,
            headers={
                "Accept": "application/json",
                "User-Agent": "OWNERA-public-opportunity-intake/0.1",
            },
            method="GET",
        )
        try:
            with urlopen(request, timeout=self.TIMEOUT_SECONDS) as response:
                final_url = urlparse(response.geturl())
                if (
                    final_url.scheme != "https"
                    or final_url.hostname is None
                    or not (
                        final_url.hostname == "immunefi.com"
                        or final_url.hostname.endswith(".immunefi.com")
                    )
                ):
                    raise SourceAdapterError("Immunefi catalog redirected outside its domain")
                content_type = response.headers.get("Content-Type", "").lower()
                if "application/json" not in content_type:
                    raise SourceAdapterError("Immunefi catalog did not return JSON")
                payload = response.read(self.MAX_RESPONSE_BYTES + 1)
        except HTTPError as exc:
            raise SourceAdapterError(
                f"Immunefi catalog returned HTTP {exc.code}"
            ) from exc
        except URLError as exc:
            raise SourceAdapterError("Immunefi catalog request failed") from exc
        if len(payload) > self.MAX_RESPONSE_BYTES:
            raise SourceAdapterError("Immunefi catalog response exceeds size limit")
        return payload

    @staticmethod
    def _parse_datetime(value: object, field: str) -> datetime:
        if not isinstance(value, str) or not value.strip():
            raise SourceAdapterError(f"Immunefi record has invalid {field}")
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError as exc:
            raise SourceAdapterError(f"Immunefi record has invalid {field}") from exc
        if parsed.tzinfo is None:
            raise SourceAdapterError(f"Immunefi record {field} must include timezone")
        return parsed.astimezone(timezone.utc)

    @staticmethod
    def _string_tuple(value: object, field: str) -> tuple[str, ...]:
        if value is None:
            return ()
        if not isinstance(value, list) or any(
            not isinstance(item, str) or not item.strip() for item in value
        ):
            raise SourceAdapterError(f"Immunefi record has invalid {field}")
        return tuple(value)

    @staticmethod
    def _bounded_text(value: object, limit: int) -> str:
        if not isinstance(value, str):
            return ""
        return value[:limit]

    def _snapshot(
        self,
        record: dict,
        *,
        fetched_at: datetime,
        slug: str,
        project: str,
    ) -> str:
        assets = record.get("assets", [])
        rewards = record.get("rewards", [])
        if not isinstance(assets, list) or not isinstance(rewards, list):
            raise SourceAdapterError("Immunefi record has invalid assets or rewards")
        safe_assets = []
        for asset in assets[:30]:
            if not isinstance(asset, dict):
                raise SourceAdapterError("Immunefi record contains an invalid asset")
            safe_assets.append(
                {
                    "url": self._bounded_text(asset.get("url"), 500),
                    "type": self._bounded_text(asset.get("type"), 80),
                }
            )
        safe_rewards = []
        for reward in rewards[:20]:
            if not isinstance(reward, dict):
                raise SourceAdapterError("Immunefi record contains an invalid reward")
            safe_rewards.append(
                {
                    "assetType": self._bounded_text(reward.get("assetType"), 80),
                    "level": self._bounded_text(reward.get("level"), 40),
                    "payout": self._bounded_text(reward.get("payout"), 160),
                    "pocRequired": reward.get("pocRequired"),
                }
            )
        snapshot = {
            "source": IMMUNEFI_CATALOG_URL,
            "retrieved_at": fetched_at.isoformat(),
            "project": project,
            "slug": slug,
            "max_bounty_ceiling": record.get("maxBounty"),
            "rewards_token": self._bounded_text(record.get("rewardsToken"), 80),
            "program_types": record.get("programType") or [],
            "project_types": record.get("projectType") or [],
            "ecosystems": record.get("ecosystem") or [],
            "languages": record.get("language") or [],
            "kyc_required": record["kyc"],
            "invite_only": record["inviteOnly"],
            "paused": record["isPaused"],
            "launch_date": record["launchDate"],
            "end_date": record["endDate"],
            "assets_count": len(assets),
            "assets_preview": safe_assets,
            "assets_preview_truncated": len(assets) > len(safe_assets),
            "rewards": safe_rewards,
            "rewards_truncated": len(rewards) > len(safe_rewards),
            "program_overview_excerpt": self._bounded_text(
                record.get("programOverview"), 3_000
            ),
            "rules_excerpt": self._bounded_text(
                record.get("outOfScopeAndRules"), 3_000
            ),
        }
        encoded = json.dumps(
            snapshot,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
        if len(encoded) > 16_384:
            snapshot["program_overview_excerpt"] = snapshot[
                "program_overview_excerpt"
            ][:1_000]
            snapshot["rules_excerpt"] = snapshot["rules_excerpt"][:1_000]
            snapshot["assets_preview"] = safe_assets[:10]
            snapshot["rewards"] = safe_rewards[:10]
            snapshot["assets_preview_truncated"] = len(assets) > len(
                snapshot["assets_preview"]
            )
            snapshot["rewards_truncated"] = len(rewards) > len(snapshot["rewards"])
            encoded = json.dumps(
                snapshot,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
                allow_nan=False,
            )
        if len(encoded) > 16_384:
            raise SourceAdapterError("bounded Immunefi evidence snapshot is too large")
        return encoded

    def ingest(
        self,
        payload: bytes,
        *,
        now: datetime | None = None,
    ) -> tuple[DiscoveredBounty, ...]:
        fetched_at = now or datetime.now(timezone.utc)
        if fetched_at.tzinfo is None:
            raise ValueError("now must be timezone-aware")
        fetched_at = fetched_at.astimezone(timezone.utc)
        try:
            records = json.loads(payload)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise SourceAdapterError("Immunefi catalog is not valid JSON") from exc
        if not isinstance(records, list) or len(records) > self.MAX_CANDIDATES:
            raise SourceAdapterError("Immunefi catalog has an invalid top-level shape")

        candidates: list[DiscoveredBounty] = []
        for record in records:
            if not isinstance(record, dict):
                raise SourceAdapterError("Immunefi catalog contains a non-object record")
            required = ("project", "slug", "launchDate", "endDate", "isPaused", "inviteOnly", "kyc")
            if any(key not in record for key in required):
                raise SourceAdapterError("Immunefi record is missing required fields")
            project = record["project"]
            slug = record["slug"]
            if (
                not isinstance(project, str)
                or not project.strip()
                or not isinstance(slug, str)
                or not slug.strip()
                or "/" in slug
                or "\\" in slug
            ):
                raise SourceAdapterError("Immunefi record has invalid project identity")
            if any(not isinstance(record[key], bool) for key in ("isPaused", "inviteOnly", "kyc")):
                raise SourceAdapterError("Immunefi record has invalid program flags")
            launch_date = self._parse_datetime(record["launchDate"], "launchDate")
            end_date = (
                self._parse_datetime(record["endDate"], "endDate")
                if record["endDate"] is not None
                else None
            )
            if (
                record["isPaused"]
                or record["inviteOnly"]
                or launch_date > fetched_at
                or (end_date is not None and end_date <= fetched_at)
            ):
                continue

            max_bounty = record.get("maxBounty")
            if max_bounty is not None and (
                isinstance(max_bounty, bool) or not isinstance(max_bounty, int) or max_bounty < 0
            ):
                raise SourceAdapterError("Immunefi record has invalid maxBounty")
            program_types = self._string_tuple(record.get("programType"), "programType")
            project_types = self._string_tuple(record.get("projectType"), "projectType")
            ecosystems = self._string_tuple(record.get("ecosystem"), "ecosystem")
            languages = self._string_tuple(record.get("language"), "language")
            source_url = f"https://immunefi.com/bug-bounty/{quote(slug, safe='-_')}/"
            opportunity_id = uuid4()
            snapshot = self._snapshot(
                record, fetched_at=fetched_at, slug=slug, project=project
            )
            evidence = self._evidence_registry.capture(
                opportunity_id=opportunity_id,
                source_name=self.SOURCE_NAME,
                source_url=source_url,
                content_snapshot=snapshot,
            )
            candidates.append(
                DiscoveredBounty(
                    opportunity_id=opportunity_id,
                    evidence_id=evidence.evidence_id,
                    project=project,
                    slug=slug,
                    source_url=source_url,
                    max_bounty_ceiling=(
                        Decimal(max_bounty) if max_bounty is not None else None
                    ),
                    program_types=program_types,
                    project_types=project_types,
                    ecosystems=ecosystems,
                    languages=languages,
                    kyc_required=record["kyc"],
                    invite_only=record["inviteOnly"],
                    launch_date=launch_date,
                    end_date=end_date,
                    assets_count=len(record.get("assets", [])),
                    captured_at=fetched_at,
                )
            )
        return tuple(candidates)

    def discover(self) -> tuple[DiscoveredBounty, ...]:
        """Fetch the current catalog and capture eligible listings as PENDING evidence."""
        return self.ingest(self.fetch_payload())
