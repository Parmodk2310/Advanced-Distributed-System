import pytest

from distsys.utils.config import Settings


def test_phase6_observability_defaults_are_safe():
    settings = Settings()
    assert settings.observability_enabled is False
    assert settings.observability_host == "127.0.0.1"
    assert settings.observability_port == 9100
    assert settings.metrics_enabled is True
    assert settings.tracing_enabled is False
    assert settings.otel_exporter_otlp_endpoint == "http://127.0.0.1:4318"
    assert settings.otel_service_name == "distsys-node"
    assert settings.otel_trace_sample_ratio == pytest.approx(0.10)
    assert settings.otel_export_timeout_seconds == pytest.approx(2.0)


def test_phase6_config_validation_rejects_invalid_values():
    with pytest.raises(ValueError):
        Settings(observability_port=0)
    with pytest.raises(ValueError):
        Settings(otel_trace_sample_ratio=1.01)
    with pytest.raises(ValueError):
        Settings(otel_export_timeout_seconds=0)
