import pytest

from distsys.cluster.member import SeedAddress
from distsys.utils.config import Settings


def test_cluster_defaults_keep_phase2_standalone_behavior():
    settings = Settings()
    assert settings.cluster_enabled is False
    assert settings.cluster_seeds == ()
    assert settings.cluster_virtual_nodes == 64
    assert settings.cluster_probe_interval_seconds == 1.0
    assert settings.cluster_ping_timeout_seconds == 0.25
    assert settings.cluster_indirect_timeout_seconds == 0.50
    assert settings.cluster_indirect_probe_count == 2
    assert settings.cluster_suspicion_timeout_seconds == 3.0
    assert settings.cluster_dead_retention_seconds == 30.0
    assert settings.cluster_gossip_interval_seconds == 1.0


def test_cluster_env_parses_seed_list(monkeypatch):
    monkeypatch.setenv("CLUSTER_ENABLED", "true")
    monkeypatch.setenv(
        "CLUSTER_SEEDS",
        "127.0.0.1:18000, 127.0.0.1:18001",
    )

    settings = Settings.from_env()

    assert settings.cluster_enabled is True
    assert settings.cluster_seeds == (
        SeedAddress("127.0.0.1", 18000),
        SeedAddress("127.0.0.1", 18001),
    )


def test_dead_retention_must_exceed_suspicion_timeout():
    with pytest.raises(ValueError, match="dead retention"):
        Settings(
            cluster_suspicion_timeout_seconds=3.0,
            cluster_dead_retention_seconds=3.0,
        )


def test_virtual_nodes_must_be_positive():
    with pytest.raises(ValueError, match="virtual nodes"):
        Settings(cluster_virtual_nodes=0)
