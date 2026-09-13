from dataclasses import replace

import pytest

from distsys.cluster.member import MemberStatus, SeedAddress
from distsys.crdt_client import CrdtClient
from distsys.node import DistributedNode
from tests.integration.cluster_helpers import cluster_settings, wait_until
from tests.integration.tls_helpers import client_context, generate_dev_certs


def secure_crdt_settings(*, node_id: str, port: int, certs, seeds=()):
    return replace(
        cluster_settings(node_id=node_id, port=port, seeds=seeds),
        crdt_enabled=True,
        crdt_replication_factor=2,
        crdt_replication_workers=1,
        crdt_anti_entropy_interval_seconds=0.05,
        persistence_enabled=False,
        etcd_enabled=False,
        tls_enabled=True,
        mtls_required=True,
        tls_ca_file=str(certs / "ca" / "ca.crt"),
        tls_cert_file=str(certs / node_id / "node.crt"),
        tls_key_file=str(certs / node_id / "node.key"),
    )


@pytest.mark.asyncio
async def test_mtls_cluster_join_and_crdt_replication(
    unused_tcp_port_factory,
    tmp_path,
):
    certs = generate_dev_certs(tmp_path)
    port0 = unused_tcp_port_factory()
    port1 = unused_tcp_port_factory()
    node0 = DistributedNode(secure_crdt_settings(node_id="node-0", port=port0, certs=certs))
    node1 = DistributedNode(
        secure_crdt_settings(
            node_id="node-1",
            port=port1,
            certs=certs,
            seeds=(SeedAddress("127.0.0.1", port0, "node-0"),),
        )
    )
    try:
        await node0.start()
        await node1.start()

        async def converged() -> bool:
            for node in (node0, node1):
                if node.cluster_service is None:
                    return False
                snapshot = await node.cluster_service.membership.snapshot()
                if {m.node_id for m in snapshot if m.status is MemberStatus.ALIVE} != {
                    "node-0",
                    "node-1",
                }:
                    return False
            return True

        await wait_until(converged, timeout_seconds=2.0)

        client = CrdtClient(
            port=port0,
            timeout_seconds=2.0,
            ssl_context=client_context(certs, "crdt-client"),
            server_hostname="node-0",
        )
        result = await client.increment("secure.replication", amount=4)
        assert result.value == 4

        async def replicated() -> bool:
            assert node1.crdt_service is not None
            entry = await node1.crdt_service.store.get("secure.replication")
            return entry is not None and entry.state.value() == 4

        await wait_until(replicated, timeout_seconds=2.0)
    finally:
        await node1.stop()
        await node0.stop()
