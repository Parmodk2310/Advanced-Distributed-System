import pytest

from distsys.utils.config import Settings


def test_crdt_defaults_are_conservative():
    settings = Settings()
    assert settings.crdt_enabled is False
    assert settings.crdt_replication_factor == 3
    assert settings.crdt_replication_queue_capacity == 500
    assert settings.crdt_replication_workers == 2
    assert settings.crdt_replication_retry_max_attempts == 3
    assert settings.crdt_replication_retry_base_delay_seconds == 0.05
    assert settings.crdt_replication_retry_max_delay_seconds == 1.0
    assert settings.crdt_anti_entropy_interval_seconds == 2.0
    assert settings.crdt_anti_entropy_batch_size == 100


def test_enabling_crdt_requires_cluster():
    with pytest.raises(ValueError, match="CRDT_ENABLED requires CLUSTER_ENABLED"):
        Settings(crdt_enabled=True, cluster_enabled=False)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"crdt_replication_factor": 0},
        {"crdt_replication_queue_capacity": 0},
        {"crdt_replication_workers": 0},
        {"crdt_replication_retry_max_attempts": 0},
        {"crdt_replication_retry_base_delay_seconds": -0.1},
        {"crdt_replication_retry_max_delay_seconds": -0.1},
        {"crdt_anti_entropy_interval_seconds": 0},
        {"crdt_anti_entropy_batch_size": 0},
    ],
)
def test_invalid_crdt_settings_rejected(kwargs):
    with pytest.raises(ValueError):
        Settings(**kwargs)


def test_retry_max_must_not_be_less_than_base():
    with pytest.raises(ValueError):
        Settings(
            crdt_replication_retry_base_delay_seconds=1.0,
            crdt_replication_retry_max_delay_seconds=0.5,
        )
