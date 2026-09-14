from __future__ import annotations

import importlib.util
from pathlib import Path


def load_patcher(root: Path):
    path = root / "patches" / "apply_existing_file_changes.py"
    spec = importlib.util.spec_from_file_location("phase6_patcher", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_patch_config_collapses_duplicate_phase6_from_env_blocks(tmp_path: Path) -> None:
    bundle_root = Path(__file__).resolve().parents[3]
    patcher = load_patcher(bundle_root)
    config = tmp_path / "src/distsys/utils/config.py"
    config.parent.mkdir(parents=True)
    phase6_kwargs = """            observability_enabled=_env_bool("OBSERVABILITY_ENABLED", False),
            observability_host=os.getenv("OBSERVABILITY_HOST", "127.0.0.1"),
            observability_port=int(os.getenv("OBSERVABILITY_PORT", "9100")),
            metrics_enabled=_env_bool("METRICS_ENABLED", True),
            tracing_enabled=_env_bool("TRACING_ENABLED", False),
            otel_exporter_otlp_endpoint=os.getenv(
                "OTEL_EXPORTER_OTLP_ENDPOINT", "http://127.0.0.1:4318"
            ),
            otel_service_name=os.getenv("OTEL_SERVICE_NAME", "distsys-node"),
            otel_trace_sample_ratio=float(os.getenv("OTEL_TRACE_SAMPLE_RATIO", "0.10")),
            otel_export_timeout_seconds=float(os.getenv("OTEL_EXPORT_TIMEOUT_SECONDS", "2.0")),
"""
    config.write_text(
        """from __future__ import annotations
import os
from dataclasses import dataclass

@dataclass(slots=True, frozen=True)
class Settings:
    tls_min_version: str = "TLSv1.3"
    observability_enabled: bool = False
    observability_host: str = "127.0.0.1"
    observability_port: int = 9100
    metrics_enabled: bool = True
    tracing_enabled: bool = False
    otel_exporter_otlp_endpoint: str = "http://127.0.0.1:4318"
    otel_service_name: str = "distsys-node"
    otel_trace_sample_ratio: float = 0.10
    otel_export_timeout_seconds: float = 2.0

    def __post_init__(self) -> None:
        if self.tls_enabled and not (self.tls_ca_file and self.tls_cert_file and self.tls_key_file):
            raise ValueError("TLS_ENABLED requires CA, certificate, and private-key files")
        if not 1 <= self.observability_port <= 65535:
            raise ValueError("observability_port must be in 1..65535")
        if not 0.0 <= self.otel_trace_sample_ratio <= 1.0:
            raise ValueError("otel_trace_sample_ratio must be in [0.0, 1.0]")
        if self.otel_export_timeout_seconds <= 0:
            raise ValueError("otel_export_timeout_seconds must be greater than zero")
        if not self.otel_service_name.strip():
            raise ValueError("otel_service_name must not be empty")

    @classmethod
    def from_env(cls) -> Settings:
        return cls(
            tls_min_version=os.getenv("TLS_MIN_VERSION", "TLSv1.3"),
"""
        + phase6_kwargs
        + phase6_kwargs
        + phase6_kwargs
        + """        )
""",
        encoding="utf-8",
    )

    patcher.patch_config(tmp_path)
    text = config.read_text(encoding="utf-8")
    assert text.count("observability_enabled=_env_bool") == 1
    assert text.count("otel_exporter_otlp_endpoint=os.getenv") == 1
    compile(text, str(config), "exec")

    patcher.patch_config(tmp_path)
    assert config.read_text(encoding="utf-8") == text


def test_peer_upgrade_repairs_missing_routing_imports(tmp_path: Path) -> None:
    bundle_root = Path(__file__).resolve().parents[3]
    patcher = load_patcher(bundle_root)

    cluster = tmp_path / "src/distsys/cluster/peer_client.py"
    cluster.parent.mkdir(parents=True)
    cluster.write_text(
        """from distsys.chaos.routing import resolve_peer_endpoint

class PeerClient:
    async def _exchange_endpoint(
        self,
        host: str,
        port: int,
        message: Message,
        *,
        timeout_seconds: float,
        expected_node_id: str | None = None,
    ) -> Message:
        tracing = getattr(self, "tracing", None)
        metrics = getattr(self, "metrics", None)
        if (
            metrics is None
            and (tracing is None or not tracing.enabled)
            and not peer_routing_enabled()
        ):
            return await self._exchange_endpoint_raw(
                host,
                port,
                message,
                timeout_seconds=timeout_seconds,
                expected_node_id=expected_node_id,
            )

    async def _exchange_endpoint_raw(
        self,
        host: str,
        port: int,
        message: Message,
        *,
        timeout_seconds: float,
        expected_node_id: str | None = None,
    ) -> Message:
        return message
""",
        encoding="utf-8",
    )
    patcher.patch_cluster_peer(tmp_path)
    text = cluster.read_text(encoding="utf-8")
    assert "from distsys.chaos.routing import peer_routing_enabled, resolve_peer_endpoint" in text
    before = text
    patcher.patch_cluster_peer(tmp_path)
    assert cluster.read_text(encoding="utf-8") == before

    crdt = tmp_path / "src/distsys/replication/peer_client.py"
    crdt.parent.mkdir(parents=True)
    crdt.write_text(
        """from distsys.chaos.routing import resolve_peer_endpoint

class CrdtPeerClient:
    async def _exchange(
        self,
        peer: ClusterMember,
        message: Message,
        *,
        timeout_seconds: float,
    ) -> Message:
        tracing = getattr(self, "tracing", None)
        metrics = getattr(self, "metrics", None)
        if (
            metrics is None
            and (tracing is None or not tracing.enabled)
            and not peer_routing_enabled()
        ):
            return await self._exchange_raw(peer, message, timeout_seconds=timeout_seconds)

    async def _exchange_raw(
        self,
        peer: ClusterMember,
        message: Message,
        *,
        timeout_seconds: float,
    ) -> Message:
        return message
""",
        encoding="utf-8",
    )
    patcher.patch_crdt_peer(tmp_path)
    text = crdt.read_text(encoding="utf-8")
    assert "from distsys.chaos.routing import peer_routing_enabled, resolve_peer_endpoint" in text
    before = text
    patcher.patch_crdt_peer(tmp_path)
    assert crdt.read_text(encoding="utf-8") == before


def test_replication_metrics_accepts_already_instrumented_methods(tmp_path: Path) -> None:
    bundle_root = Path(__file__).resolve().parents[3]
    patcher = load_patcher(bundle_root)
    service = tmp_path / "src/distsys/replication/service.py"
    service.parent.mkdir(parents=True)
    service.write_text(
        """from typing import Any

class ReplicationService:
    def __init__(self) -> None:
        self._replicator_started = False
        self._anti_entropy_started = False
        self.metrics: Any | None = None

    async def reserve_write(self, key, replica_ids):
        pairs = tuple((node_id, key) for node_id in replica_ids if node_id != self.local_node_id)
        reservation = await self.outbox.reserve(pairs)
        if self.metrics is not None:
            self.metrics.set_replication_queue_depth(await self.outbox.pending_count())
        return reservation

    async def cancel_write(self, reservation):
        await self.outbox.cancel(reservation)
        if self.metrics is not None:
            self.metrics.set_replication_queue_depth(await self.outbox.pending_count())

    async def publish_write(self, reservation, entry):
        await self.outbox.publish(reservation, {entry.key: entry})
        if self.metrics is not None:
            self.metrics.set_replication_queue_depth(await self.outbox.pending_count())

    async def ensure_causal(self, key, required, deadline):
        try:
            result = await self.repair.ensure(key, required, deadline)
        except Exception:
            if self.metrics is not None:
                self.metrics.causal_repair("failure")
            raise
        if self.metrics is not None:
            self.metrics.causal_repair("success" if result.contacted_nodes else "skipped")
        return result

    async def reconcile_peer(self, peer, keys=None):
        try:
            result = await self.anti_entropy.reconcile_peer(peer, keys)
        except Exception:
            if self.metrics is not None:
                self.metrics.anti_entropy_repair("failure")
            raise
        if self.metrics is not None:
            self.metrics.anti_entropy_repair("success")
        return result
""",
        encoding="utf-8",
    )
    before = service.read_text(encoding="utf-8")
    patcher.patch_replication_metrics(tmp_path)
    assert service.read_text(encoding="utf-8") == before


def test_persistence_metrics_accepts_already_instrumented_store(tmp_path: Path) -> None:
    bundle_root = Path(__file__).resolve().parents[3]
    patcher = load_patcher(bundle_root)
    store = tmp_path / "src/distsys/persistence/durable_store.py"
    store.parent.mkdir(parents=True)
    store.write_text(
        """from __future__ import annotations

import time
from typing import Any

class DurableCrdtStore:
    def __init__(self, clock) -> None:
        self.clock = clock
        self.metrics: Any | None = None

    async def commit_local(self, entry, frontier, deadline=None):
        causal_state = object()
        started = time.perf_counter()
        try:
            await self.repository.commit_mutation(entry, causal_state, deadline)
        except Exception:
            if self.metrics is not None:
                self.metrics.persistence("write", time.perf_counter() - started, failed=True)
            raise
        if self.metrics is not None:
            self.metrics.persistence("write", time.perf_counter() - started)
        return await self.memory.replace(entry, expected_type=entry.crdt_type)
""",
        encoding="utf-8",
    )
    before = store.read_text(encoding="utf-8")
    patcher.patch_persistence_metrics(tmp_path)
    assert store.read_text(encoding="utf-8") == before


def test_phase5_timing_patch_only_relaxes_dead_waits(tmp_path: Path) -> None:
    bundle_root = Path(__file__).resolve().parents[3]
    patcher = load_patcher(bundle_root)

    failure = tmp_path / "tests/integration/test_failure_detection.py"
    failure.parent.mkdir(parents=True)
    failure.write_text(
        """async def test_failure():
    try:
        async def suspect() -> bool:
            return True

        await wait_until(suspect, timeout_seconds=2.0)

        async def dead() -> bool:
            current = await node0.cluster_service.membership.get("node-1")
            return current is not None and current.status is MemberStatus.DEAD

        await wait_until(dead, timeout_seconds=2.0)
    finally:
        pass
""",
        encoding="utf-8",
    )

    rejoin = tmp_path / "tests/integration/test_node_rejoin.py"
    rejoin.parent.mkdir(parents=True, exist_ok=True)
    rejoin.write_text(
        """async def test_rejoin():
    try:
        async def dead() -> bool:
            current = await service.membership.get("node-1")
            return current is not None and current.status is MemberStatus.DEAD

        await wait_until(dead, timeout_seconds=2.0)

        async def rejoined() -> bool:
            return True

        await wait_until(rejoined, timeout_seconds=2.0)
    finally:
        pass
""",
        encoding="utf-8",
    )

    patcher.patch_phase5_timing_tests(tmp_path)
    failure_text = failure.read_text(encoding="utf-8")
    rejoin_text = rejoin.read_text(encoding="utf-8")
    assert "wait_until(suspect, timeout_seconds=2.0)" in failure_text
    assert "wait_until(dead, timeout_seconds=3.0)" in failure_text
    assert "wait_until(dead, timeout_seconds=3.0)" in rejoin_text
    assert "wait_until(rejoined, timeout_seconds=2.0)" in rejoin_text

    patcher.patch_phase5_timing_tests(tmp_path)
    assert failure.read_text(encoding="utf-8") == failure_text
    assert rejoin.read_text(encoding="utf-8") == rejoin_text
