"""Configuration management with environment variables."""

import os
from dataclasses import dataclass, field
from typing import List, Tuple, Optional


@dataclass
class NodeConfig:
    """Node configuration loaded from environment."""
    node_id: str = field(default_factory=lambda: os.getenv("NODE_ID", "node-0"))
    host: str = field(default_factory=lambda: os.getenv("NODE_HOST", "0.0.0.0"))
    port: int = field(default_factory=lambda: int(os.getenv("NODE_PORT", "8000")))
    peers: List[Tuple[str, int]] = field(default_factory=list)
    
    # TLS
    use_tls: bool = field(default_factory=lambda: os.getenv("USE_TLS", "false").lower() == "true")
    cert_dir: str = field(default_factory=lambda: os.getenv("CERT_DIR", "certs"))
    
    # etcd
    etcd_endpoints: Optional[List[str]] = field(default_factory=lambda: 
        os.getenv("ETCD_ENDPOINTS", "http://localhost:2379").split(",") if os.getenv("ETCD_ENDPOINTS") else None)
    
    # Metrics
    metrics_port: int = field(default_factory=lambda: int(os.getenv("METRICS_PORT", "9090")))
    
    # Performance
    max_workers: int = field(default_factory=lambda: int(os.getenv("MAX_WORKERS", str(os.cpu_count() - 1))))
    max_queue_depth: int = field(default_factory=lambda: int(os.getenv("MAX_QUEUE_DEPTH", "500")))
    
    # Resilience
    circuit_failure_threshold: int = field(default_factory=lambda: int(os.getenv("CIRCUIT_FAILURE_THRESHOLD", "3")))
    circuit_recovery_timeout: float = field(default_factory=lambda: float(os.getenv("CIRCUIT_RECOVERY_TIMEOUT", "8.0")))
    
    # Gossip
    gossip_interval: float = field(default_factory=lambda: float(os.getenv("GOSSIP_INTERVAL", "2.0")))
    failure_timeout: float = field(default_factory=lambda: float(os.getenv("FAILURE_TIMEOUT", "15.0")))
    
    @classmethod
    def from_env(cls) -> "NodeConfig":
        """Load configuration from environment variables."""
        config = cls()
        
        # Parse peers from environment
        peers_str = os.getenv("PEERS", "")
        if peers_str:
            config.peers = []
            for peer in peers_str.split(","):
                host, port = peer.strip().split(":")
                config.peers.append((host, int(port)))
        
        return config
    
    def to_dict(self) -> dict:
        return {
            "node_id": self.node_id,
            "host": self.host,
            "port": self.port,
            "peers": [f"{h}:{p}" for h, p in self.peers],
            "use_tls": self.use_tls,
            "etcd_endpoints": self.etcd_endpoints,
            "metrics_port": self.metrics_port,
            "max_workers": self.max_workers,
        }