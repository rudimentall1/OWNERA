"""Explainable, read-only triage of captured Immunefi bounty evidence.

Scores indicate research fit, not exploit probability, expected payout, or eligibility.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True)
class TriageResult:
    opportunity_id: str
    evidence_id: str
    project: str
    slug: str
    source_url: str
    score: int
    tier: str
    reasons: tuple[str, ...]
    blockers: tuple[str, ...]
    manual_checks: tuple[str, ...]
    max_bounty_ceiling: str | None
    captured_at: str

    def to_dict(self) -> dict:
        value = asdict(self)
        value["reasons"] = list(self.reasons)
        value["blockers"] = list(self.blockers)
        value["manual_checks"] = list(self.manual_checks)
        return value


_EVM_ECOSYSTEMS = {
    "ETH", "Ethereum", "Arbitrum", "Optimism", "Polygon", "Base",
    "BSC", "Avalanche", "Gnosis", "Linea", "Scroll", "zkSync",
    "Fantom", "Celo", "Mantle", "Moonbeam", "Metis",
}


def score_snapshot(snapshot: dict, *, opportunity_id: str, evidence_id: str,
                   source_url: str, captured_at: str, lifecycle_status: str) -> TriageResult:
    score = 0
    reasons: list[str] = []
    blockers: list[str] = []
    manual: list[str] = [
        "Verify current program terms, scope, exclusions, and submission rules.",
        "Confirm researcher eligibility, jurisdiction, KYC, and payout conditions.",
        "Confirm the exact asset and source-code revision are in scope before testing.",
    ]

    if lifecycle_status != "ACTIVE" or snapshot.get("paused"):
        blockers.append("program_not_active")
    else:
        score += 10
        reasons.append("active_public_program:+10")
    if snapshot.get("invite_only"):
        blockers.append("invite_only")
    else:
        score += 10
        reasons.append("public_participation:+10")

    languages = {str(x).casefold() for x in snapshot.get("languages", [])}
    if "solidity" in languages:
        score += 20
        reasons.append("solidity_skill_fit:+20")
    elif languages.intersection({"rust", "vyper", "move"}):
        score += 10
        reasons.append("adjacent_smart_contract_language:+10")
    else:
        manual.append("Assess language/toolchain fit before spending research time.")

    ecosystems = {str(x) for x in snapshot.get("ecosystems", [])}
    if ecosystems.intersection(_EVM_ECOSYSTEMS):
        score += 15
        reasons.append("evm_ecosystem_fit:+15")

    assets = snapshot.get("assets_preview", [])
    repo_assets = [a for a in assets if isinstance(a, dict) and "github.com/" in str(a.get("url", "")).lower()]
    if len(repo_assets) >= 3:
        score += 10
        reasons.append("multiple_public_source_repository_references:+10")
    elif repo_assets:
        score += 5
        reasons.append("public_source_repository_reference:+5")
    else:
        manual.append("Locate and pin an authoritative source repository or verified source code.")

    asset_count = snapshot.get("assets_count", 0)
    if isinstance(asset_count, int) and 1 <= asset_count <= 10:
        score += 10
        reasons.append("small_catalog_asset_set:+10")
    elif isinstance(asset_count, int) and 11 <= asset_count <= 30:
        score += 7
        reasons.append("manageable_catalog_asset_count:+7")
    elif isinstance(asset_count, int) and 31 <= asset_count <= 100:
        score += 3
        reasons.append("moderate_catalog_asset_count:+3")
    elif isinstance(asset_count, int) and asset_count > 100:
        manual.append("Narrow the large asset set to one defensible, in-scope target.")

    if "Smart Contract" in snapshot.get("program_types", []):
        score += 10
        reasons.append("smart_contract_program:+10")
    if snapshot.get("kyc_required"):
        score -= 5
        reasons.append("kyc_required:-5")
        manual.append("KYC is a participation/payout dependency; verify before investing time.")
    else:
        score += 5
        reasons.append("no_catalog_kyc_flag:+5")

    overview = str(snapshot.get("program_overview_excerpt", ""))
    if len(overview.strip()) >= 1_500:
        score += 5
        reasons.append("detailed_program_context:+5")
    elif len(overview.strip()) >= 500:
        score += 3
        reasons.append("usable_program_context:+3")
    else:
        manual.append("Program evidence is thin; retrieve the full official rules before assessment.")

    score = max(0, min(100, score))
    tier = "RESEARCH_FIRST" if score >= 85 else "REVIEW" if score >= 65 else "LOW_PRIORITY"
    if blockers:
        tier = "BLOCKED"
    if snapshot.get("assets_preview_truncated"):
        manual.append("Asset preview is truncated; inspect the complete official asset list.")
    if snapshot.get("rewards_truncated"):
        manual.append("Reward schedule preview is truncated; inspect the full schedule.")
    if not snapshot.get("rewards") or all(not str(x.get("payout", "")).strip() for x in snapshot.get("rewards", []) if isinstance(x, dict)):
        manual.append("Catalog does not expose usable payout tiers; do not infer expected reward from maximum ceiling.")

    ceiling = snapshot.get("max_bounty_ceiling")
    return TriageResult(
        opportunity_id=opportunity_id,
        evidence_id=evidence_id,
        project=str(snapshot.get("project", "Unknown")),
        slug=str(snapshot.get("slug", "")),
        source_url=source_url,
        score=score,
        tier=tier,
        reasons=tuple(reasons),
        blockers=tuple(blockers),
        manual_checks=tuple(dict.fromkeys(manual)),
        max_bounty_ceiling=str(ceiling) if ceiling is not None else None,
        captured_at=captured_at,
    )


def rank_immunefi(database_path: str | Path, *, limit: int = 10) -> list[TriageResult]:
    if limit < 1 or limit > 100:
        raise ValueError("limit must be between 1 and 100")
    connection = sqlite3.connect(str(database_path), timeout=10)
    connection.row_factory = sqlite3.Row
    try:
        rows = connection.execute(
            """SELECT e.evidence_id,e.opportunity_id,e.source_url,e.captured_at,
                      e.content_snapshot,o.lifecycle_status
               FROM opportunity_evidence e
               JOIN source_observations o ON o.latest_evidence_id=e.evidence_id
               WHERE e.source_name='Immunefi public bounty catalog'
               ORDER BY e.captured_at DESC"""
        ).fetchall()
    finally:
        connection.close()

    results = []
    for row in rows:
        snapshot = json.loads(row["content_snapshot"])
        results.append(score_snapshot(
            snapshot,
            opportunity_id=row["opportunity_id"],
            evidence_id=row["evidence_id"],
            source_url=row["source_url"],
            captured_at=row["captured_at"],
            lifecycle_status=row["lifecycle_status"],
        ))
    results.sort(key=lambda item: (item.tier == "BLOCKED", -item.score, item.project.casefold()))
    return results[:limit]
