"""OpenTelemetry runtime with W3C context propagation and no-op fallback."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import MutableMapping
from dataclasses import dataclass
from typing import Any

from opentelemetry import trace
from opentelemetry.context import Context
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.trace.sampling import ALWAYS_ON, ParentBased, TraceIdRatioBased
from opentelemetry.trace import Tracer
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

logger = logging.getLogger("distsys.observability.tracing")


def _trace_export_endpoint(base_endpoint: str) -> str:
    endpoint = base_endpoint.rstrip("/")
    if endpoint.endswith("/v1/traces"):
        return endpoint
    return f"{endpoint}/v1/traces"


@dataclass(slots=True)
class TracingRuntime:
    tracer: Tracer
    enabled: bool = False
    provider: TracerProvider | None = None

    @classmethod
    def create(cls, settings: Any, node_id: str) -> TracingRuntime:
        if not bool(settings.tracing_enabled):
            return cls(
                trace.NoOpTracerProvider().get_tracer(str(settings.otel_service_name)),
                False,
            )
        try:
            from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
                OTLPSpanExporter,
            )

            resource = Resource.create(
                {
                    "service.name": str(settings.otel_service_name),
                    "service.instance.id": node_id,
                    "service.version": "0.6.0",
                }
            )
            provider = TracerProvider(
                resource=resource,
                sampler=ParentBased(TraceIdRatioBased(float(settings.otel_trace_sample_ratio))),
            )
            exporter = OTLPSpanExporter(
                endpoint=_trace_export_endpoint(str(settings.otel_exporter_otlp_endpoint)),
                timeout=float(settings.otel_export_timeout_seconds),
            )
            provider.add_span_processor(BatchSpanProcessor(exporter))
            return cls(
                provider.get_tracer(str(settings.otel_service_name)),
                True,
                provider,
            )
        except Exception:
            logger.exception("tracing initialization failed; continuing with no-op tracing")
            return cls(
                trace.NoOpTracerProvider().get_tracer(str(settings.otel_service_name)),
                False,
            )

    @classmethod
    def for_test(cls, node_id: str = "test-node") -> TracingRuntime:
        provider = TracerProvider(
            resource=Resource.create(
                {"service.name": "distsys-test", "service.instance.id": node_id}
            ),
            sampler=ALWAYS_ON,
        )
        return cls(provider.get_tracer("distsys-test"), True, provider)

    def inject(self, carrier: MutableMapping[str, str]) -> None:
        if not self.enabled:
            return
        TraceContextTextMapPropagator().inject(carrier)

    def extract(self, carrier: MutableMapping[str, str] | dict[str, str]) -> Context:
        if not self.enabled:
            return Context()
        return TraceContextTextMapPropagator().extract(carrier)

    async def shutdown(self, timeout_seconds: float | None = None) -> None:
        provider, self.provider = self.provider, None
        if provider is None:
            return
        timeout = 2.0 if timeout_seconds is None else max(0.001, float(timeout_seconds))
        try:
            await asyncio.wait_for(
                asyncio.to_thread(provider.shutdown),
                timeout=timeout,
            )
        except TimeoutError:
            logger.warning(
                "OpenTelemetry shutdown exceeded %.3fs; abandoning flush",
                timeout,
            )
        except Exception:
            logger.exception("OpenTelemetry shutdown failed; service shutdown continues")
