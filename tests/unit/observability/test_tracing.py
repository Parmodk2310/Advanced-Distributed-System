from dataclasses import dataclass

from distsys.observability.tracing import TracingRuntime


@dataclass(frozen=True)
class Settings:
    tracing_enabled: bool = False
    otel_exporter_otlp_endpoint: str = "http://127.0.0.1:4318"
    otel_service_name: str = "distsys-node"
    otel_trace_sample_ratio: float = 0.1
    otel_export_timeout_seconds: float = 2.0


def test_disabled_runtime_is_noop_safe():
    runtime = TracingRuntime.create(Settings(), "node-a")
    carrier: dict[str, str] = {}
    runtime.inject(carrier)
    assert carrier == {}
    assert runtime.enabled is False


def test_w3c_inject_extract_round_trip_with_active_span():
    runtime = TracingRuntime.for_test("node-a")
    with runtime.tracer.start_as_current_span("root") as root:
        carrier: dict[str, str] = {}
        runtime.inject(carrier)
        assert carrier["traceparent"].startswith("00-")
        context = runtime.extract(carrier)
        with runtime.tracer.start_as_current_span("child", context=context) as child:
            assert child.get_span_context().trace_id == root.get_span_context().trace_id
