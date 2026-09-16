"""Environment-based distributed-system settings."""

from __future__ import annotations

import os
from dataclasses import dataclass

from distsys.cluster.member import SeedAddress
from distsys.protocol.framing import DEFAULT_MAX_FRAME_SIZE


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    value = raw.strip().lower()
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{name} must be a boolean value")


def _env_seeds() -> tuple[SeedAddress, ...]:
    raw = os.getenv("CLUSTER_SEEDS", "").strip()
    if not raw:
        return ()
    return tuple(SeedAddress.parse(item.strip()) for item in raw.split(",") if item.strip())


def _env_endpoints(name: str, default: str) -> tuple[str, ...]:
    raw = os.getenv(name, default).strip()
    return tuple(item.strip() for item in raw.split(",") if item.strip())


@dataclass(slots=True, frozen=True)
class Settings:
    node_id: str = "node-0"
    host: str = "127.0.0.1"
    advertise_host: str = ""
    port: int = 8000
    max_frame_size: int = DEFAULT_MAX_FRAME_SIZE
    request_timeout_seconds: float = 5.0
    log_level: str = "INFO"

    cpu_workers: int = 2
    cpu_queue_capacity: int = 200
    rate_limit_rps: float = 500.0
    rate_limit_burst: int = 100

    retry_max_attempts: int = 3
    retry_base_delay_seconds: float = 0.05
    retry_max_delay_seconds: float = 1.0

    circuit_breaker_failure_threshold: int = 5
    circuit_breaker_recovery_seconds: float = 10.0

    cluster_enabled: bool = False
    cluster_seeds: tuple[SeedAddress, ...] = ()
    cluster_virtual_nodes: int = 64
    cluster_probe_interval_seconds: float = 1.0
    cluster_ping_timeout_seconds: float = 0.25
    cluster_indirect_timeout_seconds: float = 0.50
    cluster_indirect_probe_count: int = 2
    cluster_suspicion_timeout_seconds: float = 3.0
    cluster_dead_retention_seconds: float = 30.0
    cluster_gossip_interval_seconds: float = 1.0

    crdt_enabled: bool = False
    crdt_replication_factor: int = 3
    crdt_replication_queue_capacity: int = 500
    crdt_replication_workers: int = 2
    crdt_replication_retry_max_attempts: int = 3
    crdt_replication_retry_base_delay_seconds: float = 0.05
    crdt_replication_retry_max_delay_seconds: float = 1.0
    crdt_anti_entropy_interval_seconds: float = 2.0
    crdt_anti_entropy_batch_size: int = 100

    persistence_enabled: bool = True
    persistence_db_path: str = "./data/node.db"
    persistence_queue_capacity: int = 100
    persistence_busy_timeout_seconds: float = 5.0
    persistence_sqlite_synchronous: str = "NORMAL"

    etcd_enabled: bool = True
    etcd_endpoints: tuple[str, ...] = ("http://127.0.0.1:2379",)
    etcd_namespace: str = "/distsys/v1"
    etcd_lease_ttl_seconds: int = 15
    etcd_renew_interval_seconds: float = 5.0

    tls_enabled: bool = False
    mtls_required: bool = False
    tls_ca_file: str = ""
    tls_cert_file: str = ""
    tls_key_file: str = ""
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
        if self.cpu_workers < 1:
            raise ValueError("cpu_workers must be at least 1")
        if self.cpu_queue_capacity < 1:
            raise ValueError("cpu_queue_capacity must be at least 1")
        if self.rate_limit_rps <= 0:
            raise ValueError("rate_limit_rps must be greater than zero")
        if self.rate_limit_burst < 1:
            raise ValueError("rate_limit_burst must be at least 1")
        if self.request_timeout_seconds <= 0:
            raise ValueError("request_timeout_seconds must be greater than zero")
        if self.cluster_virtual_nodes < 1:
            raise ValueError("cluster virtual nodes must be at least 1")
        if self.cluster_probe_interval_seconds <= 0:
            raise ValueError("cluster probe interval must be greater than zero")
        if self.cluster_ping_timeout_seconds <= 0:
            raise ValueError("cluster ping timeout must be greater than zero")
        if self.cluster_indirect_timeout_seconds <= 0:
            raise ValueError("cluster indirect timeout must be greater than zero")
        if self.cluster_indirect_probe_count < 0:
            raise ValueError("cluster indirect probe count cannot be negative")
        if self.cluster_suspicion_timeout_seconds <= 0:
            raise ValueError("cluster suspicion timeout must be greater than zero")
        if self.cluster_dead_retention_seconds <= self.cluster_suspicion_timeout_seconds:
            raise ValueError("cluster dead retention must exceed suspicion timeout")
        if self.cluster_gossip_interval_seconds <= 0:
            raise ValueError("cluster gossip interval must be greater than zero")

        if self.crdt_enabled and not self.cluster_enabled:
            raise ValueError("CRDT_ENABLED requires CLUSTER_ENABLED")
        if self.crdt_replication_factor < 1:
            raise ValueError("crdt replication factor must be at least 1")
        if self.crdt_replication_queue_capacity < 1:
            raise ValueError("crdt replication queue capacity must be at least 1")
        if self.crdt_replication_workers < 1:
            raise ValueError("crdt replication workers must be at least 1")
        if self.crdt_replication_retry_max_attempts < 1:
            raise ValueError("crdt replication retry attempts must be at least 1")
        if self.crdt_replication_retry_base_delay_seconds < 0:
            raise ValueError("crdt replication retry base delay cannot be negative")
        if self.crdt_replication_retry_max_delay_seconds < 0:
            raise ValueError("crdt replication retry max delay cannot be negative")
        if (
            self.crdt_replication_retry_max_delay_seconds
            < self.crdt_replication_retry_base_delay_seconds
        ):
            raise ValueError("crdt replication retry max delay cannot be less than base delay")
        if self.crdt_anti_entropy_interval_seconds <= 0:
            raise ValueError("crdt anti entropy interval must be greater than zero")
        if self.crdt_anti_entropy_batch_size < 1:
            raise ValueError("crdt anti entropy batch size must be at least 1")

        if self.persistence_queue_capacity < 1:
            raise ValueError("persistence queue capacity must be at least 1")
        if self.persistence_busy_timeout_seconds <= 0:
            raise ValueError("persistence busy timeout must be greater than zero")
        if self.persistence_sqlite_synchronous.upper() not in {"OFF", "NORMAL", "FULL", "EXTRA"}:
            raise ValueError("unsupported SQLite synchronous mode")

        if self.etcd_enabled and not self.etcd_endpoints:
            raise ValueError("etcd endpoints must not be empty when etcd is enabled")
        if not self.etcd_namespace.strip("/"):
            raise ValueError("etcd namespace must not be empty")
        if self.etcd_lease_ttl_seconds <= 0:
            raise ValueError("etcd lease TTL must be positive")
        if self.etcd_renew_interval_seconds <= 0:
            raise ValueError("etcd renew interval must be positive")
        if self.etcd_renew_interval_seconds >= self.etcd_lease_ttl_seconds:
            raise ValueError("etcd renew interval must be less than lease TTL")

        if self.mtls_required and not self.tls_enabled:
            raise ValueError("MTLS_REQUIRED requires TLS_ENABLED")
        if self.tls_min_version != "TLSv1.3":
            raise ValueError("Phase 5 secure profile requires TLSv1.3")
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
            node_id=os.getenv("NODE_ID", "node-0"),
            host=os.getenv("NODE_HOST", "127.0.0.1"),
            advertise_host=os.getenv("NODE_ADVERTISE_HOST", ""),
            port=int(os.getenv("NODE_PORT", "8000")),
            max_frame_size=int(os.getenv("MAX_FRAME_SIZE", str(DEFAULT_MAX_FRAME_SIZE))),
            request_timeout_seconds=float(os.getenv("REQUEST_TIMEOUT_SECONDS", "5.0")),
            log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
            cpu_workers=int(os.getenv("CPU_WORKERS", "2")),
            cpu_queue_capacity=int(os.getenv("CPU_QUEUE_CAPACITY", "200")),
            rate_limit_rps=float(os.getenv("RATE_LIMIT_RPS", "500.0")),
            rate_limit_burst=int(os.getenv("RATE_LIMIT_BURST", "100")),
            retry_max_attempts=int(os.getenv("RETRY_MAX_ATTEMPTS", "3")),
            retry_base_delay_seconds=float(os.getenv("RETRY_BASE_DELAY_SECONDS", "0.05")),
            retry_max_delay_seconds=float(os.getenv("RETRY_MAX_DELAY_SECONDS", "1.0")),
            circuit_breaker_failure_threshold=int(
                os.getenv("CIRCUIT_BREAKER_FAILURE_THRESHOLD", "5")
            ),
            circuit_breaker_recovery_seconds=float(
                os.getenv("CIRCUIT_BREAKER_RECOVERY_SECONDS", "10.0")
            ),
            cluster_enabled=_env_bool("CLUSTER_ENABLED", False),
            cluster_seeds=_env_seeds(),
            cluster_virtual_nodes=int(os.getenv("CLUSTER_VIRTUAL_NODES", "64")),
            cluster_probe_interval_seconds=float(
                os.getenv("CLUSTER_PROBE_INTERVAL_SECONDS", "1.0")
            ),
            cluster_ping_timeout_seconds=float(os.getenv("CLUSTER_PING_TIMEOUT_SECONDS", "0.25")),
            cluster_indirect_timeout_seconds=float(
                os.getenv("CLUSTER_INDIRECT_TIMEOUT_SECONDS", "0.50")
            ),
            cluster_indirect_probe_count=int(os.getenv("CLUSTER_INDIRECT_PROBE_COUNT", "2")),
            cluster_suspicion_timeout_seconds=float(
                os.getenv("CLUSTER_SUSPICION_TIMEOUT_SECONDS", "3.0")
            ),
            cluster_dead_retention_seconds=float(
                os.getenv("CLUSTER_DEAD_RETENTION_SECONDS", "30.0")
            ),
            cluster_gossip_interval_seconds=float(
                os.getenv("CLUSTER_GOSSIP_INTERVAL_SECONDS", "1.0")
            ),
            crdt_enabled=_env_bool("CRDT_ENABLED", False),
            crdt_replication_factor=int(os.getenv("CRDT_REPLICATION_FACTOR", "3")),
            crdt_replication_queue_capacity=int(
                os.getenv("CRDT_REPLICATION_QUEUE_CAPACITY", "500")
            ),
            crdt_replication_workers=int(os.getenv("CRDT_REPLICATION_WORKERS", "2")),
            crdt_replication_retry_max_attempts=int(
                os.getenv("CRDT_REPLICATION_RETRY_MAX_ATTEMPTS", "3")
            ),
            crdt_replication_retry_base_delay_seconds=float(
                os.getenv("CRDT_REPLICATION_RETRY_BASE_DELAY_SECONDS", "0.05")
            ),
            crdt_replication_retry_max_delay_seconds=float(
                os.getenv("CRDT_REPLICATION_RETRY_MAX_DELAY_SECONDS", "1.0")
            ),
            crdt_anti_entropy_interval_seconds=float(
                os.getenv("CRDT_ANTI_ENTROPY_INTERVAL_SECONDS", "2.0")
            ),
            crdt_anti_entropy_batch_size=int(os.getenv("CRDT_ANTI_ENTROPY_BATCH_SIZE", "100")),
            persistence_enabled=_env_bool("PERSISTENCE_ENABLED", True),
            persistence_db_path=os.getenv("PERSISTENCE_DB_PATH", "./data/node.db"),
            persistence_queue_capacity=int(os.getenv("PERSISTENCE_QUEUE_CAPACITY", "100")),
            persistence_busy_timeout_seconds=float(
                os.getenv("PERSISTENCE_BUSY_TIMEOUT_SECONDS", "5.0")
            ),
            persistence_sqlite_synchronous=os.getenv(
                "PERSISTENCE_SQLITE_SYNCHRONOUS", "NORMAL"
            ).upper(),
            etcd_enabled=_env_bool("ETCD_ENABLED", True),
            etcd_endpoints=_env_endpoints("ETCD_ENDPOINTS", "http://127.0.0.1:2379"),
            etcd_namespace=os.getenv("ETCD_NAMESPACE", "/distsys/v1"),
            etcd_lease_ttl_seconds=int(os.getenv("ETCD_LEASE_TTL_SECONDS", "15")),
            etcd_renew_interval_seconds=float(os.getenv("ETCD_RENEW_INTERVAL_SECONDS", "5")),
            tls_enabled=_env_bool("TLS_ENABLED", False),
            mtls_required=_env_bool("MTLS_REQUIRED", False),
            tls_ca_file=os.getenv("TLS_CA_FILE", ""),
            tls_cert_file=os.getenv("TLS_CERT_FILE", ""),
            tls_key_file=os.getenv("TLS_KEY_FILE", ""),
            tls_min_version=os.getenv("TLS_MIN_VERSION", "TLSv1.3"),
            observability_enabled=_env_bool("OBSERVABILITY_ENABLED", False),
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
        )
