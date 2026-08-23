#!/usr/bin/env python3
"""Benchmark suite for the distributed system."""

import asyncio
import time
import statistics
import argparse
from typing import List, Dict
import aiohttp

from src.client import DistributedClient


class Benchmark:
    def __init__(self, nodes: List[Dict], use_tls: bool = False):
        self.client = DistributedClient(nodes, use_tls=use_tls)
        self.results: List[Dict] = []
    
    async def run_echo_benchmark(self, concurrency: int = 100, total: int = 10000):
        """Benchmark echo requests."""
        print(f"\\n🚀 Echo Benchmark: {total} requests, {concurrency} concurrent")
        
        sem = asyncio.Semaphore(concurrency)
        latencies: List[float] = []
        errors = 0
        
        async def single_request(i: int):
            async with sem:
                start = time.time()
                try:
                    await self.client.request("echo", {"data": f"msg-{i}", "delay": 0.001})
                    latencies.append((time.time() - start) * 1000)
                except Exception:
                    errors += 1
        
        start = time.time()
        await asyncio.gather(*[single_request(i) for i in range(total)])
        elapsed = time.time() - start
        
        throughput = total / elapsed
        avg_lat = statistics.mean(latencies) if latencies else 0
        p95 = statistics.quantiles(latencies, n=20)[18] if len(latencies) >= 20 else avg_lat
        p99 = statistics.quantiles(latencies, n=100)[98] if len(latencies) >= 100 else avg_lat
        
        print(f"  Throughput: {throughput:.0f} req/s")
        print(f"  Avg Latency: {avg_lat:.2f}ms")
        print(f"  P95 Latency: {p95:.2f}ms")
        print(f"  P99 Latency: {p99:.2f}ms")
        print(f"  Errors: {errors}/{total} ({errors/total*100:.2f}%)")
        
        return {
            "test": "echo",
            "throughput": throughput,
            "avg_latency_ms": avg_lat,
            "p95_latency_ms": p95,
            "p99_latency_ms": p99,
            "error_rate": errors / total
        }
    
    async def run_cpu_benchmark(self, concurrency: int = 50, total: int = 500):
        """Benchmark CPU-intensive hash requests."""
        print(f"\\n🔥 CPU Benchmark: {total} hash requests, {concurrency} concurrent")
        
        sem = asyncio.Semaphore(concurrency)
        latencies: List[float] = []
        
        async def single_request(i: int):
            async with sem:
                start = time.time()
                await self.client.request("hash", {"data": f"data-{i}", "iterations": 5000})
                latencies.append((time.time() - start) * 1000)
        
        start = time.time()
        await asyncio.gather(*[single_request(i) for i in range(total)])
        elapsed = time.time() - start
        
        throughput = total / elapsed
        avg_lat = statistics.mean(latencies)
        
        print(f"  Throughput: {throughput:.0f} req/s")
        print(f"  Avg Latency: {avg_lat:.2f}ms")
        
        return {
            "test": "cpu_hash",
            "throughput": throughput,
            "avg_latency_ms": avg_lat
        }
    
    async def run_batch_benchmark(self, batch_size: int = 100, total_batches: int = 100):
        """Benchmark batch processing."""
        print(f"\\n📦 Batch Benchmark: {total_batches} batches of {batch_size}")
        
        latencies: List[float] = []
        
        for i in range(total_batches):
            requests = [{"task": "echo", "data": f"b{i}-{j}", "delay": 0.001} for j in range(batch_size)]
            start = time.time()
            await self.client.batch_request(requests)
            latencies.append((time.time() - start) * 1000)
        
        avg_lat = statistics.mean(latencies)
        throughput = (total_batches * batch_size) / sum(latencies) * 1000
        
        print(f"  Throughput: {throughput:.0f} req/s")
        print(f"  Avg Batch Time: {avg_lat:.2f}ms")
        
        return {
            "test": "batch",
            "throughput": throughput,
            "avg_batch_time_ms": avg_lat
        }
    
    async def run_crdt_benchmark(self, operations: int = 1000):
        """Benchmark CRDT operations."""
        print(f"\\n🔄 CRDT Benchmark: {operations} operations")
        
        start = time.time()
        for i in range(operations):
            await self.client.request("crdt_op", {
                "crdt_id": "benchmark-counter",
                "crdt_type": "g_counter",
                "operation": "increment",
                "value": 1
            })
        elapsed = time.time() - start
        
        throughput = operations / elapsed
        print(f"  Throughput: {throughput:.0f} ops/s")
        
        return {
            "test": "crdt",
            "throughput": throughput
        }
    
    async def run_all(self):
        """Run all benchmarks."""
        print("=" * 60)
        print("DISTRIBUTED SYSTEM BENCHMARK SUITE")
        print("=" * 60)
        
        results = []
        results.append(await self.run_echo_benchmark())
        results.append(await self.run_cpu_benchmark())
        results.append(await self.run_batch_benchmark())
        results.append(await self.run_crdt_benchmark())
        
        print("\\n" + "=" * 60)
        print("SUMMARY")
        print("=" * 60)
        for r in results:
            print(f"{r['test']}: {r['throughput']:.0f} ops/s")
        
        await self.client.close()
        return results


async def main():
    parser = argparse.ArgumentParser(description="Benchmark distributed system")
    parser.add_argument("--host", default="127.0.0.1", help="Node host")
    parser.add_argument("--port", type=int, default=8000, help="Node port")
    parser.add_argument("--nodes", type=int, default=1, help="Number of nodes")
    parser.add_argument("--tls", action="store_true", help="Use TLS")
    args = parser.parse_args()
    
    nodes = []
    for i in range(args.nodes):
        nodes.append({
            "host": args.host,
            "port": args.port + i,
            "node_id": f"node-{i}"
        })
    
    benchmark = Benchmark(nodes, use_tls=args.tls)
    await benchmark.run_all()


if __name__ == "__main__":
    asyncio.run(main())