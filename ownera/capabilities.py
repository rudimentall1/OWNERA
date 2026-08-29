"""Capability tiers for OWNERA.

Tiers describe product entitlements, not a bypass around the security model.
Every capability still has to pass policy, risk, authorization and execution
controls. Subscription status can never grant access to the Sovereign Reserve.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum


class AutonomyLevel(IntEnum):
    OBSERVER = 0
    AUTOPILOT = 1
    PERSONAL = 2
    AUTONOMOUS = 3
    SOVEREIGN = 4


@dataclass(frozen=True)
class CapabilitySet:
    analyze: bool
    monitor: bool
    recurring_payments: bool
    voice_transfers: bool
    crypto_transfers: bool
    investment_proposals: bool
    autonomous_investing: bool
    autonomous_defi: bool
    advanced_security: bool
    quantum_safe_migration: bool


LEVEL_CAPABILITIES: dict[AutonomyLevel, CapabilitySet] = {
    AutonomyLevel.OBSERVER: CapabilitySet(
        analyze=True,
        monitor=True,
        recurring_payments=False,
        voice_transfers=False,
        crypto_transfers=False,
        investment_proposals=True,
        autonomous_investing=False,
        autonomous_defi=False,
        advanced_security=False,
        quantum_safe_migration=False,
    ),
    AutonomyLevel.AUTOPILOT: CapabilitySet(
        analyze=True,
        monitor=True,
        recurring_payments=True,
        voice_transfers=False,
        crypto_transfers=False,
        investment_proposals=True,
        autonomous_investing=False,
        autonomous_defi=False,
        advanced_security=True,
        quantum_safe_migration=False,
    ),
    AutonomyLevel.PERSONAL: CapabilitySet(
        analyze=True,
        monitor=True,
        recurring_payments=True,
        voice_transfers=True,
        crypto_transfers=True,
        investment_proposals=True,
        autonomous_investing=False,
        autonomous_defi=False,
        advanced_security=True,
        quantum_safe_migration=False,
    ),
    AutonomyLevel.AUTONOMOUS: CapabilitySet(
        analyze=True,
        monitor=True,
        recurring_payments=True,
        voice_transfers=True,
        crypto_transfers=True,
        investment_proposals=True,
        autonomous_investing=True,
        autonomous_defi=True,
        advanced_security=True,
        quantum_safe_migration=True,
    ),
    AutonomyLevel.SOVEREIGN: CapabilitySet(
        analyze=True,
        monitor=True,
        recurring_payments=True,
        voice_transfers=True,
        crypto_transfers=True,
        investment_proposals=True,
        autonomous_investing=True,
        autonomous_defi=True,
        advanced_security=True,
        quantum_safe_migration=True,
    ),
}


def capabilities_for(level: AutonomyLevel) -> CapabilitySet:
    """Return product capabilities for an autonomy level."""
    return LEVEL_CAPABILITIES[level]


# Deliberately absent from CapabilitySet:
# - sovereign_reserve_withdrawal
# - sovereign_reserve_transfer
# - sovereign_reserve_reconfigure
# These are security invariants and must never become commercial entitlements.
