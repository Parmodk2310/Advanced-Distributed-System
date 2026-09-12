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
