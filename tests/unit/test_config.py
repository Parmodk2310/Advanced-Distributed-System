from distsys.proto import messages_pb2
from distsys.utils.config import Settings


def test_phase2_error_codes_exist():
    assert messages_pb2.OVERLOADED == 5
    assert messages_pb2.RATE_LIMITED == 6


def test_phase2_settings_defaults_are_conservative():
    settings = Settings()
    assert settings.cpu_workers == 2
    assert settings.cpu_queue_capacity == 200
    assert settings.rate_limit_rps == 500.0
    assert settings.rate_limit_burst == 100
    assert settings.request_timeout_seconds == 5.0
    assert settings.retry_max_attempts == 3
    assert settings.retry_base_delay_seconds == 0.05
    assert settings.retry_max_delay_seconds == 1.0
    assert settings.circuit_breaker_failure_threshold == 5
    assert settings.circuit_breaker_recovery_seconds == 10.0


def test_phase5_persistence_defaults():
    settings = Settings()
    assert settings.persistence_enabled is True
    assert settings.persistence_db_path == "./data/node.db"
    assert settings.persistence_queue_capacity == 100
    assert settings.persistence_busy_timeout_seconds == 5.0
    assert settings.persistence_sqlite_synchronous == "NORMAL"


def test_invalid_persistence_settings_rejected():
    import pytest

    with pytest.raises(ValueError):
        Settings(persistence_queue_capacity=0)
    with pytest.raises(ValueError):
        Settings(persistence_busy_timeout_seconds=0)
    with pytest.raises(ValueError):
        Settings(persistence_sqlite_synchronous="FAST")


def test_phase5_etcd_defaults():
    settings = Settings()
    assert settings.etcd_enabled is True
    assert settings.etcd_endpoints == ("http://127.0.0.1:2379",)
    assert settings.etcd_namespace == "/distsys/v1"
    assert settings.etcd_lease_ttl_seconds == 15
    assert settings.etcd_renew_interval_seconds == 5.0


def test_invalid_etcd_settings_rejected():
    import pytest

    with pytest.raises(ValueError):
        Settings(etcd_lease_ttl_seconds=0)
    with pytest.raises(ValueError):
        Settings(etcd_renew_interval_seconds=15, etcd_lease_ttl_seconds=15)
    with pytest.raises(ValueError):
        Settings(etcd_namespace="")
    with pytest.raises(ValueError):
        Settings(etcd_endpoints=())


def test_phase5_tls_defaults():
    settings = Settings()
    assert settings.tls_enabled is False
    assert settings.mtls_required is False
    assert settings.tls_min_version == "TLSv1.3"


def test_invalid_tls_settings_rejected():
    import pytest

    with pytest.raises(ValueError):
        Settings(mtls_required=True, tls_enabled=False)
    with pytest.raises(ValueError):
        Settings(tls_enabled=True, tls_ca_file="", tls_cert_file="", tls_key_file="")
    with pytest.raises(ValueError):
        Settings(tls_min_version="TLSv1.2")
