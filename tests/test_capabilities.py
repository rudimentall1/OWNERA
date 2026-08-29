from ownera.capabilities import AutonomyLevel, capabilities_for


def test_autonomy_levels_are_ordered():
    assert AutonomyLevel.OBSERVER < AutonomyLevel.AUTOPILOT < AutonomyLevel.PERSONAL < AutonomyLevel.AUTONOMOUS < AutonomyLevel.SOVEREIGN


def test_observer_cannot_execute_transfers():
    caps = capabilities_for(AutonomyLevel.OBSERVER)
    assert not caps.voice_transfers
    assert not caps.crypto_transfers
    assert not caps.autonomous_investing


def test_autonomous_level_enables_treasury_features():
    caps = capabilities_for(AutonomyLevel.AUTONOMOUS)
    assert caps.voice_transfers
    assert caps.crypto_transfers
    assert caps.autonomous_investing
    assert caps.autonomous_defi
    assert caps.quantum_safe_migration


def test_sovereign_reserve_is_not_a_capability():
    caps = capabilities_for(AutonomyLevel.SOVEREIGN)
    assert not hasattr(caps, "sovereign_reserve_withdrawal")
    assert not hasattr(caps, "sovereign_reserve_transfer")
    assert not hasattr(caps, "sovereign_reserve_reconfigure")
