"""Prometheus metrics export for observability."""

import time
from typing import Dict
from collections import deque


class PrometheusMetrics:
    """
    Prometheus-compatible metrics collector.
    
    Exposes metrics in OpenMetrics format for scraping by Prometheus.
    Includes counters, gauges, histograms, and summaries.
    """
    
    def __init__(self, node_id: str, port: int = 9090):
        self.node_id = node_id
        self.port = port
        
        # Counters (only increase)
        self.counters: Dict[str, float] = {
            "requests_total": 0,
            "requests_failed_total": 0,
            "bytes_received_total": 0,
            "bytes_sent_total": 0,
            "circuit_trips_total": 0,
            "gossip_messages_total": 0,
        }
        
        # Gauges (can go up/down)
        self.gauges: Dict[str, float] = {
            "active_connections": 0,
            "queue_depth": 0,
            "backpressure_load": 0.0,
            "worker_pool_pending": 0,
            "cluster_members": 0,
        }
        
        # Histogram buckets for latency (in ms)
        self.latency_buckets = [0.5, 1, 2.5, 5, 10, 25, 50, 100, 250, 500, 1000, 2500, 5000]
        self.latency_counts: Dict[str, int] = {str(b): 0 for b in self.latency_buckets}
        self.latency_sum = 0.0
        self.latency_total = 0
        
        # Recent latencies for p50/p95/p99
        self.latency_window: deque = deque(maxlen=10000)
    
    def increment(self, name: str, value: float = 1.0):
        if name in self.counters:
            self.counters[name] += value
    
    def gauge(self, name: str, value: float):
        if name in self.gauges:
            self.gauges[name] = value
    
    def observe_latency(self, latency_ms: float):
        """Record a latency observation."""
        self.latency_sum += latency_ms
        self.latency_total += 1
        self.latency_window.append(latency_ms)
        
        for bucket in self.latency_buckets:
            if latency_ms <= bucket:
                self.latency_counts[str(bucket)] += 1
    
    def percentile(self, p: float) -> float:
        """Calculate percentile from latency window."""
        if not self.latency_window:
            return 0.0
        sorted_lat = sorted(self.latency_window)
        idx = int(len(sorted_lat) * p / 100)
        return sorted_lat[min(idx, len(sorted_lat) - 1)]
    
    def export(self) -> str:
        """Export metrics in Prometheus text format."""
        lines = []
        lines.append(f"# HELP distsys_info Node information")
        lines.append(f"# TYPE distsys_info gauge")
        lines.append(f'distsys_info{{node_id="{self.node_id}"}} 1')
        
        # Counters
        for name, value in self.counters.items():
            lines.append(f"# HELP distsys_{name} Counter")
            lines.append(f"# TYPE distsys_{name} counter")
            lines.append(f'distsys_{name}{{node_id="{self.node_id}"}} {value}')
        
        # Gauges
        for name, value in self.gauges.items():
            lines.append(f"# HELP distsys_{name} Gauge")
            lines.append(f"# TYPE distsys_{name} gauge")
            lines.append(f'distsys_{name}{{node_id="{self.node_id}"}} {value}')
        
        # Latency histogram
        lines.append("# HELP distsys_request_latency_ms Request latency")
        lines.append("# TYPE distsys_request_latency_ms histogram")
        for bucket in self.latency_buckets:
            count = self.latency_counts[str(bucket)]
            lines.append(f'distsys_request_latency_ms_bucket{{node_id="{self.node_id}",le="{bucket}"}} {count}')
        lines.append(f'distsys_request_latency_ms_bucket{{node_id="{self.node_id}",le="+Inf"}} {self.latency_total}')
        lines.append(f'distsys_request_latency_ms_sum{{node_id="{self.node_id}"}} {self.latency_sum}')
        lines.append(f'distsys_request_latency_ms_count{{node_id="{self.node_id}"}} {self.latency_total}')
        
        # Percentiles
        lines.append("# HELP distsys_latency_p50 Median latency")
        lines.append("# TYPE distsys_latency_p50 gauge")
        lines.append(f'distsys_latency_p50{{node_id="{self.node_id}"}} {self.percentile(50)}')
        
        lines.append("# HELP distsys_latency_p95 95th percentile latency")
        lines.append("# TYPE distsys_latency_p95 gauge")
        lines.append(f'distsys_latency_p95{{node_id="{self.node_id}"}} {self.percentile(95)}')
        
        lines.append("# HELP distsys_latency_p99 99th percentile latency")
        lines.append("# TYPE distsys_latency_p99 gauge")
        lines.append(f'distsys_latency_p99{{node_id="{self.node_id}"}} {self.percentile(99)}')
        
        return "\\n".join(lines) + "\\n"
    
    async def start_http_server(self):
        """Start HTTP server for Prometheus scraping."""
        from aiohttp import web
        
        async def metrics_handler(request):
            return web.Response(text=self.export(), content_type="text/plain")
        
        app = web.Application()
        app.router.add_get("/metrics", metrics_handler)
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "0.0.0.0", self.port)
        await site.start()
        print(f"Prometheus metrics on http://0.0.0.0:{self.port}/metrics")
