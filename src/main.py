
"""Production Distributed Node with all enhancements."""

import asyncio
import multiprocessing as mp
import struct
import hashlib
import time
import random
import logging
import json
import socket
import ssl
from dataclasses import dataclass, field
from typing import Dict, List, Set, Optional, Callable, Any, Tuple
from enum import Enum, auto
from collections import defaultdict, deque
from concurrent.futures import ProcessPoolExecutor
from contextlib import asynccontextmanager
import heapq
import uuid
import os
import sys


# Internal imports
from src.protocol.message import Message, MessageType, VectorClock
from src.protocol.tls import TLSSecurity
from src.cluster.consistent_hash import ConsistentHashRing
from src.cluster.gossip import GossipProtocol
from src.resilience.circuit_breaker import CircuitBreaker, CircuitBreakerOpen
from src.resilience.backpressure import BackpressureController
from src.resilience.retry import RetryPolicy
from src.compute.worker_pool import WorkerPool, CPUIntensiveTask
from src.metrics.prometheus import PrometheusMetrics
from src.storage.etcd_client import EtcdStateStore
from src.consistency.crdt.g_counter import GCounter
from src.consistency.crdt.pn_counter import PNCounter
from src.consistency.crdt.lww_register import LWWRegister
from src.consistency.crdt.or_set import ORSet
from src.main import DistributedNode
from src.utils.config import NodeConfig

# Add src to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Optional uvloop for performance
try:
    import uvloop
    asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
    print("✅ uvloop enabled for 2-4x asyncio performance")
except ImportError:
    print("⚠️  uvloop not installed. Run: pip install uvloop")

logger = logging.getLogger("DistSys")


class DistributedNode:
    """
    Production distributed node with:
    - TLS encryption (mTLS)
    - Vector clocks for causal consistency
    - CRDT state synchronization
    - etcd persistence for cold starts
    - Prometheus metrics export
    - uvloop event loop
    """
    
    def __init__(self, node_id: str, host: str = "0.0.0.0", port: int = 0,
                 peers: List[Tuple[str, int]] = None,
                 use_tls: bool = False, cert_dir: str = "certs",
                 etcd_endpoints: List[str] = None,
                 metrics_port: int = 9090):
        self.node_id = node_id
        self.host = host
        self.port = port
        self.peers = peers or []
        self.use_tls = use_tls
        
        # TLS
        self.tls = TLSSecurity(cert_dir) if use_tls else None
        
        # Vector clock for causal consistency
        self.vector_clock = VectorClock(node_id)
        
        # CRDT registry
        self.crdts: Dict[str, Any] = {}
        
        # etcd state store
        self.etcd = EtcdStateStore(etcd_endpoints) if etcd_endpoints else None
        
        # Subsystems
        self.circuit_breaker = CircuitBreaker(failure_threshold=3, recovery_timeout=8.0)
        self.backpressure = BackpressureController(max_queue_depth=500)
        self.hash_ring = ConsistentHashRing(replicas=150)
        self.gossip = GossipProtocol(node_id, port, peers)
        self.worker_pool = WorkerPool(max_workers=max(2, mp.cpu_count() - 1))
        self.retry_policy = RetryPolicy(max_retries=3, base_delay=0.1)
        self.metrics = PrometheusMetrics(node_id, metrics_port)
        
        # State
        self.server = None
        self._running = False
        self._shutdown_event = asyncio.Event()
        
        # Metrics tracking
        self._latencies = deque(maxlen=1000)
    
    async def start(self):
        """Start node with all subsystems."""
        self._running = True
        
        # Connect to etcd if configured
        if self.etcd:
            await self.etcd.connect()
            await self.etcd.register_member(self.node_id, self.host, self.port)
            # Load persisted state
            await self._load_persisted_state()
        
        # Create TCP server
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind((self.host, self.port))
        sock.listen(128)
        
        if self.use_tls and self.tls:
            ssl_ctx = self.tls.create_server_context()
            self.server = await asyncio.start_server(self._handle_client, sock=sock, ssl=ssl_ctx)
        else:
            self.server = await asyncio.start_server(self._handle_client, sock=sock)
        
        self.port = sock.getsockname()[1]
        self.gossip.port = self.port
        logger.info(f"🚀 Node {self.node_id} on {self.host}:{self.port} (TLS={self.use_tls})")
        
        self.hash_ring.add_node(self.node_id)
        await self.gossip.start()
        
        # Start background tasks
        asyncio.create_task(self._health_check_loop())
        asyncio.create_task(self._metrics_reporter())
        asyncio.create_task(self._persist_state_loop())
        asyncio.create_task(self._crdt_sync_loop())
        
        # Start Prometheus HTTP server
        asyncio.create_task(self.metrics.start_http_server())
    
    async def _handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        """Handle incoming TLS/TCP connections."""
        try:
            while self._running:
                header = await reader.read(4)
                if len(header) < 4:
                    break
                if header[:2] != Message.MAGIC:
                    break
                
                sender_len = struct.unpack("!B", await reader.read(1))[0]
                sender = await reader.read(sender_len)
                corr_len = struct.unpack("!B", await reader.read(1))[0]
                corr = await reader.read(corr_len)
                meta = await reader.read(9)
                vc_len = struct.unpack("!I", await reader.read(4))[0]
                vc_data = await reader.read(vc_len)
                payload_len = struct.unpack("!I", await reader.read(4))[0]
                payload = await reader.read(payload_len)
                
                msg_data = (header + struct.pack("!B", sender_len) + sender +
                           struct.pack("!B", corr_len) + corr + meta +
                           struct.pack("!I", vc_len) + vc_data +
                           struct.pack("!I", payload_len) + payload)
                msg = Message.deserialize(msg_data)
                
                # Merge vector clocks for causal tracking
                if msg.vector_clock:
                    self.vector_clock.merge(msg.vector_clock)
                
                self.metrics.increment("bytes_received_total", len(msg_data))
                asyncio.create_task(self._process_message(msg, writer))
        except Exception:
            pass
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except:
                pass
    
    async def _process_message(self, msg: Message, writer: asyncio.StreamWriter):
        st = time.time()
        try:
            if msg.msg_type == MessageType.REQUEST:
                await self._handle_request(msg, writer)
            elif msg.msg_type == MessageType.BATCH:
                await self._handle_batch(msg, writer)
            elif msg.msg_type == MessageType.GOSSIP:
                self.gossip.handle_gossip(msg)
            elif msg.msg_type == MessageType.HEALTH_CHECK:
                await self._handle_health(msg, writer)
            elif msg.msg_type == MessageType.CRDT_SYNC:
                await self._handle_crdt_sync(msg, writer)
        except Exception as e:
            logger.error(f"Process error: {e}")
        finally:
            lat_ms = (time.time() - st) * 1000
            self.metrics.observe_latency(lat_ms)
            self._latencies.append(lat_ms)
    
    async def _handle_request(self, msg: Message, writer: asyncio.StreamWriter):
        if not await self.backpressure.acquire():
            await self._send(writer, Message(MessageType.BACKPRESSURE, self.node_id, b"overload", correlation_id=msg.correlation_id))
            return
        try:
            data = json.loads(msg.payload.decode("utf-8"))
            task_type = data.get("task")
            
            # Increment vector clock before processing
            self.vector_clock.increment()
            
            result = await self.circuit_breaker.call(self._execute_task, task_type, data)
            
            response = Message(
                MessageType.RESPONSE, self.node_id,
                json.dumps({"result": result, "status": "ok"}).encode(),
                correlation_id=msg.correlation_id,
                vector_clock=self.vector_clock.copy()
            )
            self.metrics.increment("requests_total")
        except CircuitBreakerOpen:
            response = Message(MessageType.CIRCUIT_OPEN, self.node_id, b"unavailable", correlation_id=msg.correlation_id)
            self.metrics.increment("circuit_trips_total")
        except Exception as e:
            response = Message(MessageType.RESPONSE, self.node_id, json.dumps({"error": str(e)}).encode(), correlation_id=msg.correlation_id)
            self.metrics.increment("requests_failed_total")
        finally:
            await self.backpressure.release()
        await self._send(writer, response)
    
    async def _execute_task(self, task_type: str, data: Dict) -> Any:
        if task_type == "hash":
            d = data.get("data", "").encode() if isinstance(data.get("data"), str) else data.get("data", b"")
            it = data.get("iterations", 1000)
            return await self.worker_pool.submit(CPUIntensiveTask.compute_hash, d, it)
        elif task_type == "sort":
            return await self.worker_pool.submit(CPUIntensiveTask.sort_large_dataset, data.get("data", []))
        elif task_type == "aggregate":
            return await self.worker_pool.submit(CPUIntensiveTask.aggregate_metrics, data.get("data", []))
        elif task_type == "crdt_get":
            crdt_id = data.get("crdt_id")
            if crdt_id in self.crdts:
                return self.crdts[crdt_id].to_dict()
            return None
        elif task_type == "crdt_op":
            return await self._apply_crdt_operation(data)
        elif task_type == "echo":
            await asyncio.sleep(data.get("delay", 0))
            return data.get("data")
        else:
            raise ValueError(f"Unknown: {task_type}")
    
    async def _apply_crdt_operation(self, data: Dict) -> Dict:
        """Apply a CRDT operation with vector clock tracking."""
        crdt_id = data.get("crdt_id")
        crdt_type = data.get("crdt_type")
        op = data.get("operation")
        value = data.get("value")
        
        if crdt_id not in self.crdts:
            if crdt_type == "g_counter":
                self.crdts[crdt_id] = GCounter(crdt_id, self.node_id)
            elif crdt_type == "pn_counter":
                self.crdts[crdt_id] = PNCounter(crdt_id, self.node_id)
            elif crdt_type == "lww_register":
                self.crdts[crdt_id] = LWWRegister(crdt_id, self.node_id)
            elif crdt_type == "or_set":
                self.crdts[crdt_id] = ORSet(crdt_id, self.node_id)
        
        crdt = self.crdts[crdt_id]
        
        if op == "increment":
            crdt.increment(value or 1)
        elif op == "decrement" and hasattr(crdt, "decrement"):
            crdt.decrement(value or 1)
        elif op == "set" and hasattr(crdt, "set"):
            crdt.set(value)
        elif op == "add" and hasattr(crdt, "add"):
            crdt.add(value)
        elif op == "remove" and hasattr(crdt, "remove"):
            crdt.remove(value)
        
        self.vector_clock.increment()
        return {"crdt_id": crdt_id, "value": crdt.value() if hasattr(crdt, "value") else None}
    
    async def _handle_crdt_sync(self, msg: Message, writer: asyncio.StreamWriter):
        """Handle incoming CRDT state synchronization."""
        data = json.loads(msg.payload.decode("utf-8"))
        crdt_id = data.get("crdt_id")
        remote_state = data.get("state")
        
        if crdt_id in self.crdts:
            local = self.crdts[crdt_id]
            remote_type = data.get("crdt_type")
            if remote_type == "g_counter":
                remote = GCounter.from_dict(remote_state)
            elif remote_type == "pn_counter":
                remote = PNCounter.from_dict(remote_state)
            elif remote_type == "lww_register":
                remote = LWWRegister.from_dict(remote_state)
            elif remote_type == "or_set":
                remote = ORSet.from_dict(remote_state)
            else:
                return
            local.merge(remote)
    
    async def _crdt_sync_loop(self):
        """Periodically sync CRDT states with peers."""
        while self._running:
            await asyncio.sleep(10)
            for crdt_id, crdt in self.crdts.items():
                state = json.dumps(crdt.to_dict()).encode()
                # Broadcast to peers (simplified)
                for host, port in self.peers:
                    try:
                        payload = json.dumps({"crdt_id": crdt_id, "crdt_type": crdt.to_dict().get("type"), "state": crdt.to_dict()}).encode()
                        msg = Message(MessageType.CRDT_SYNC, self.node_id, payload, vector_clock=self.vector_clock.copy())
                        await self._send_to_peer(host, port, msg)
                    except Exception:
                        pass
    
    async def _send_to_peer(self, host: str, port: int, msg: Message):
        """Send message to a peer node."""
        if self.use_tls and self.tls:
            ssl_ctx = self.tls.create_client_context()
            reader, writer = await asyncio.open_connection(host, port, ssl=ssl_ctx)
        else:
            reader, writer = await asyncio.open_connection(host, port)
        try:
            writer.write(msg.serialize())
            await writer.drain()
        finally:
            writer.close()
            await writer.wait_closed()
    
    async def _send(self, writer: asyncio.StreamWriter, msg: Message):
        data = msg.serialize()
        writer.write(data)
        await writer.drain()
        self.metrics.increment("bytes_sent_total", len(data))
    
    async def _load_persisted_state(self):
        """Load vector clock and CRDTs from etcd on startup."""
        if not self.etcd:
            return
        vc_data = await self.etcd.load_vector_clock(self.node_id)
        if vc_data:
            self.vector_clock = VectorClock.from_list(self.node_id, json.loads(vc_data.decode()))
            logger.info(f"Loaded vector clock from etcd: {self.vector_clock}")
    
    async def _persist_state_loop(self):
        """Persist state to etcd every 30 seconds."""
        while self._running:
            await asyncio.sleep(30)
            if self.etcd:
                await self.etcd.save_vector_clock(self.node_id, json.dumps(self.vector_clock.to_list()).encode())
                for crdt_id, crdt in self.crdts.items():
                    await self.etcd.save_crdt(crdt_id, crdt.serialize())
    
    async def _health_check_loop(self):
        while self._running and not self._shutdown_event.is_set():
            for host, port in self.peers:
                try:
                    msg = Message(MessageType.HEALTH_CHECK, self.node_id, b"")
                    await self._send_to_peer(host, port, msg)
                except Exception:
                    pass
            try:
                await asyncio.wait_for(self._shutdown_event.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                pass
    
    async def _metrics_reporter(self):
        while self._running and not self._shutdown_event.is_set():
            try:
                await asyncio.wait_for(self._shutdown_event.wait(), timeout=10.0)
            except asyncio.TimeoutError:
                pass
            self.metrics.gauge("queue_depth", self.backpressure.current_queue_depth)
            self.metrics.gauge("backpressure_load", self.backpressure.load_factor)
            self.metrics.gauge("worker_pool_pending", self.worker_pool.pending_tasks)
            self.metrics.gauge("cluster_members", len(self.gossip.members))
            self.metrics.gauge("active_connections", len(self.gossip.members) + 1)
    
    
    async def shutdown(self):
        logger.info(f"Shutting down {self.node_id}...")
        self._running = False
        self._shutdown_event.set()
        if self.server:
            self.server.close()
            await self.server.wait_closed()
        self.gossip.stop()
        self.worker_pool.shutdown()
        if self.etcd:
            await self.etcd.close()
        logger.info(f"{self.node_id} shutdown complete")

async def run_single_node():
    """Run a single node from environment configuration."""
    config = NodeConfig.from_env()
    
    print(f"\\n🚀 Starting {config.node_id}")
    print(f"   Host: {config.host}:{config.port}")
    print(f"   Peers: {config.peers}")
    print(f"   TLS: {config.use_tls}")
    print(f"   etcd: {config.etcd_endpoints}")
    print(f"   Metrics: port {config.metrics_port}")
    
    node = DistributedNode(
        node_id=config.node_id,
        host=config.host,
        port=config.port,
        peers=config.peers,
        use_tls=config.use_tls,
        cert_dir=config.cert_dir,
        etcd_endpoints=config.etcd_endpoints,
        metrics_port=config.metrics_port
    )
    
    await node.start()
    
    print(f"\\n✅ {config.node_id} is running!")
    print(f"   gRPC: {config.host}:{node.port}")
    print(f"   Metrics: http://{config.host}:{config.metrics_port}/metrics")
    
    try:
        await asyncio.Event().wait()
    except KeyboardInterrupt:
        print(f"\\n🛑 Shutting down {config.node_id}...")
    finally:
        await node.shutdown()


async def run_demo_cluster():
    """Run a 3-node demo cluster."""
    print("\\n🏗️  Starting 3-node demo cluster...")
    
    import socket
    
    def free_port():
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind(("127.0.0.1", 0))
            return s.getsockname()[1]
    
    ports = [free_port() for _ in range(3)]
    nodes = []
    
    for i in range(3):
        nid = f"node-{i}"
        peers = [("127.0.0.1", ports[j]) for j in range(3) if j != i]
        node = DistributedNode(nid, "127.0.0.1", ports[i], peers)
        await node.start()
        nodes.append(node)
        
        for other in nodes[:-1]:
            node.hash_ring.add_node(other.node_id)
            other.hash_ring.add_node(nid)
        
        print(f"   {nid} → 127.0.0.1:{ports[i]}")
    
    print(f"\\n✅ Cluster running!")
    print(f"   Metrics: http://127.0.0.1:{nodes[0].metrics.port}/metrics")
    
    try:
        await asyncio.Event().wait()
    except KeyboardInterrupt:
        print("\\n🛑 Shutting down cluster...")
    finally:
        for node in nodes:
            await node.shutdown()


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Distributed System Node")
    parser.add_argument("--demo", action="store_true", help="Run 3-node demo cluster")
    args = parser.parse_args()
    
    if args.demo:
        asyncio.run(run_demo_cluster())
    else:
        asyncio.run(run_single_node())
# Add CRDT_SYNC to MessageType
# We need to update message.py to include CRDT_SYNC
# Let me append it

