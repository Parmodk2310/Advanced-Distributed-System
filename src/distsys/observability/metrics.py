"""Bounded-cardinality Prometheus metrics for Phase 6."""

from __future__ import annotations

import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass

from prometheus_client import (
    CollectorRegistry,
    Counter,
    Gauge,
    GCCollector,
    Histogram,
    PlatformCollector,
    ProcessCollector,
    generate_latest,
)

HISTOGRAM_BUCKETS = (0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0)

_ALLOWED: dict[str, frozenset[str]] = {
    "message_type": frozenset({"task", "cluster", "crdt", "other"}),
    "status": frozenset(
        {
            "success",
            "error",
            "timeout",
            "overloaded",
            "rate_limited",
            "no_route",
            "unavailable",
            "other",
        }
    ),
    "component": frozenset({"compute", "replication", "persistence", "coordination", "other"}),
    "operation": frozenset(
        {
            "request",
            "forward",
            "ping",
            "gossip",
            "replicate",
            "fetch",
            "digest",
            "read",
            "write",
            "lease",
            "recover",
            "other",
        }
    ),
    "result": frozenset({"success", "failure", "skipped", "other"}),
    "phase": frozenset(
        {
            "starting",
            "restoring",
            "reconciling",
            "ready",
            "degraded",
            "failed",
            "other",
        }
    ),
    "member_status": frozenset({"alive", "suspect", "dead", "other"}),
}

_PHASE_ALIASES = {
    "opening_repository": "restoring",
    "binding": "starting",
    "coordinating": "starting",
    "joining_cluster": "starting",
    "startup_failed": "failed",
}


def normalize(kind: str, value: object) -> str:
    """Normalize one label to a fixed vocabulary; unknown values become ``other``."""
    text = str(getattr(value, "value", value)).strip().lower()
    if kind == "phase":
        text = _PHASE_ALIASES.get(text, text)
    allowed = _ALLOWED.get(kind)
    if allowed is None:
        raise KeyError(f"unknown metric label kind: {kind}")
    return text if text in allowed else "other"


@dataclass
class _Timer:
    started: float
    status: str = "success"

    def fail(self, status: str = "error") -> None:
        self.status = status


class Metrics:
    """Owns a process-local registry and all Phase 6 metric definitions.

    No method accepts unbounded label dimensions. Arbitrary values are normalized
    to ``other`` before they reach prometheus-client.
    """

    def __init__(self, node_id: str, enabled: bool = True) -> None:
        self.node_id = node_id
        self.enabled = enabled
        self.registry = CollectorRegistry(auto_describe=True)
        if not enabled:
            return

        # A private registry avoids collisions while still exposing bounded runtime
        # process metrics needed by the Phase 6 Grafana resource panels.
        ProcessCollector(registry=self.registry)
        PlatformCollector(registry=self.registry)
        GCCollector(registry=self.registry)
        self.requests_total = Counter(
            "distsys_requests_total",
            "Application requests",
            ["node_id", "message_type", "status"],
            registry=self.registry,
        )
        self.request_duration = Histogram(
            "distsys_request_duration_seconds",
            "Application request latency",
            ["node_id", "message_type"],
            buckets=HISTOGRAM_BUCKETS,
            registry=self.registry,
        )
        self.requests_inflight = Gauge(
            "distsys_requests_inflight",
            "Requests currently executing",
            ["node_id"],
            registry=self.registry,
        )
        self.rate_limited_total = Counter(
            "distsys_rate_limited_total",
            "Rate-limited requests",
            ["node_id"],
            registry=self.registry,
        )
        self.overloaded_total = Counter(
            "distsys_overloaded_total",
            "Overload events",
            ["node_id", "component"],
            registry=self.registry,
        )
        self.members = Gauge(
            "distsys_members",
            "Cluster members by status",
            ["node_id", "status"],
            registry=self.registry,
        )
        self.gossip_failures_total = Counter(
            "distsys_gossip_failures_total", "Gossip failures", ["node_id"], registry=self.registry
        )
        self.peer_rpc_total = Counter(
            "distsys_peer_rpc_total",
            "Peer RPC outcomes",
            ["node_id", "operation", "status"],
            registry=self.registry,
        )
        self.peer_rpc_duration = Histogram(
            "distsys_peer_rpc_duration_seconds",
            "Peer RPC latency",
            ["node_id", "operation"],
            buckets=HISTOGRAM_BUCKETS,
            registry=self.registry,
        )
        self.replication_queue_depth = Gauge(
            "distsys_replication_queue_depth",
            "Replication queue depth",
            ["node_id"],
            registry=self.registry,
        )
        self.replication_total = Counter(
            "distsys_replication_total",
            "Replication outcomes",
            ["node_id", "status"],
            registry=self.registry,
        )
        self.anti_entropy_repairs_total = Counter(
            "distsys_anti_entropy_repairs_total",
            "Anti-entropy repairs",
            ["node_id", "result"],
            registry=self.registry,
        )
        self.causal_repairs_total = Counter(
            "distsys_causal_repairs_total",
            "Causal repairs",
            ["node_id", "result"],
            registry=self.registry,
        )
        self.persistence_duration = Histogram(
            "distsys_persistence_duration_seconds",
            "Persistence operation latency",
            ["node_id", "operation"],
            buckets=HISTOGRAM_BUCKETS,
            registry=self.registry,
        )
        self.persistence_failures_total = Counter(
            "distsys_persistence_failures_total",
            "Persistence failures",
            ["node_id", "operation"],
            registry=self.registry,
        )
        self.recovery_phase = Gauge(
            "distsys_recovery_phase",
            "Current recovery phase (one-hot)",
            ["node_id", "phase"],
            registry=self.registry,
        )
        self.recovery_duration = Histogram(
            "distsys_recovery_duration_seconds",
            "Recovery duration",
            ["node_id", "result"],
            buckets=HISTOGRAM_BUCKETS,
            registry=self.registry,
        )
        self.coordination_healthy = Gauge(
            "distsys_coordination_healthy",
            "Coordination health (1 healthy)",
            ["node_id"],
            registry=self.registry,
        )
        self.coordination_failures_total = Counter(
            "distsys_coordination_failures_total",
            "Coordination failures",
            ["node_id", "operation"],
            registry=self.registry,
        )

        for status in ("alive", "suspect", "dead", "other"):
            self.members.labels(self.node_id, status).set(0)
        for phase in _ALLOWED["phase"]:
            self.recovery_phase.labels(self.node_id, phase).set(0)

    @staticmethod
    def normalize(kind: str, value: object) -> str:
        return normalize(kind, value)

    def request_started(self, message_type: object) -> None:
        del message_type
        if self.enabled:
            self.requests_inflight.labels(self.node_id).inc()

    def request_finished(
        self,
        message_type: object,
        status: object,
        duration_seconds: float,
    ) -> None:
        if not self.enabled:
            return
        mt = normalize("message_type", message_type)
        st = normalize("status", status)
        self.requests_inflight.labels(self.node_id).dec()
        self.requests_total.labels(self.node_id, mt, st).inc()
        self.request_duration.labels(self.node_id, mt).observe(max(0.0, duration_seconds))

    @contextmanager
    def track_request(self, message_type: object) -> Iterator[_Timer]:
        self.request_started(message_type)
        timer = _Timer(time.perf_counter())
        try:
            yield timer
        except BaseException:
            timer.status = "error"
            raise
        finally:
            self.request_finished(
                message_type,
                timer.status,
                time.perf_counter() - timer.started,
            )

    def rate_limited(self) -> None:
        if self.enabled:
            self.rate_limited_total.labels(self.node_id).inc()

    def overloaded(self, component: object) -> None:
        if self.enabled:
            self.overloaded_total.labels(self.node_id, normalize("component", component)).inc()

    def set_members(self, *, alive: int, suspect: int, dead: int) -> None:
        if not self.enabled:
            return
        for status, value in (("alive", alive), ("suspect", suspect), ("dead", dead)):
            self.members.labels(self.node_id, status).set(max(0, value))

    def gossip_failure(self) -> None:
        if self.enabled:
            self.gossip_failures_total.labels(self.node_id).inc()

    def peer_rpc(
        self,
        operation: object,
        status: object,
        duration_seconds: float,
    ) -> None:
        if not self.enabled:
            return
        op = normalize("operation", operation)
        st = normalize("status", status)
        self.peer_rpc_total.labels(self.node_id, op, st).inc()
        self.peer_rpc_duration.labels(self.node_id, op).observe(max(0.0, duration_seconds))

    @contextmanager
    def observe_peer_rpc(self, operation: object) -> Iterator[_Timer]:
        timer = _Timer(time.perf_counter())
        try:
            yield timer
        except BaseException:
            timer.status = "error"
            raise
        finally:
            self.peer_rpc(operation, timer.status, time.perf_counter() - timer.started)

    def set_replication_queue_depth(self, depth: int) -> None:
        if self.enabled:
            self.replication_queue_depth.labels(self.node_id).set(max(0, depth))

    def replication(self, status: object) -> None:
        if self.enabled:
            self.replication_total.labels(self.node_id, normalize("status", status)).inc()

    def anti_entropy_repair(self, result: object) -> None:
        if self.enabled:
            self.anti_entropy_repairs_total.labels(self.node_id, normalize("result", result)).inc()

    def causal_repair(self, result: object) -> None:
        if self.enabled:
            self.causal_repairs_total.labels(self.node_id, normalize("result", result)).inc()

    def persistence(
        self,
        operation: object,
        duration_seconds: float,
        *,
        failed: bool = False,
    ) -> None:
        if not self.enabled:
            return
        op = normalize("operation", operation)
        self.persistence_duration.labels(self.node_id, op).observe(max(0.0, duration_seconds))
        if failed:
            self.persistence_failures_total.labels(self.node_id, op).inc()

    def set_recovery_phase(self, phase: object) -> None:
        if not self.enabled:
            return
        current = normalize("phase", phase)
        for candidate in _ALLOWED["phase"]:
            self.recovery_phase.labels(self.node_id, candidate).set(
                1 if candidate == current else 0
            )

    def observe_recovery(self, result: object, duration_seconds: float) -> None:
        if self.enabled:
            self.recovery_duration.labels(self.node_id, normalize("result", result)).observe(
                max(0.0, duration_seconds)
            )

    def set_coordination(self, healthy: bool) -> None:
        if self.enabled:
            self.coordination_healthy.labels(self.node_id).set(1 if healthy else 0)

    def coordination_failure(self, operation: object) -> None:
        if self.enabled:
            self.coordination_failures_total.labels(
                self.node_id, normalize("operation", operation)
            ).inc()

    def render(self) -> bytes:
        return generate_latest(self.registry) if self.enabled else b""
