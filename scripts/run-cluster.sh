#!/bin/bash
set -e

echo "Starting 3-node local cluster..."

# Generate certs if needed
bash certs/generate.sh

# Start nodes in background
PYTHONPATH=. python -c "
import asyncio
import sys
sys.path.insert(0, '.')
from src.main import DistributedNode

async def main():
    nodes = []
    ports = [8000, 8001, 8002]
    for i in range(3):
        nid = f'node-{i}'
        peers = [('127.0.0.1', ports[j]) for j in range(3) if j != i]
        node = DistributedNode(nid, '127.0.0.1', ports[i], peers, use_tls=True, cert_dir='certs')
        await node.start()
        nodes.append(node)
        print(f'Started {nid} on port {ports[i]}')
    
    print('\\nCluster running. Press Ctrl+C to stop.')
    try:
        await asyncio.Event().wait()
    except KeyboardInterrupt:
        pass
    finally:
        for n in nodes:
            await n.shutdown()

asyncio.run(main())
" &

CLUSTER_PID=$!
echo "Cluster PID: $CLUSTER_PID"
echo "Metrics: http://localhost:9091/metrics, http://localhost:9092/metrics, http://localhost:9093/metrics"
wait $CLUSTER_PID