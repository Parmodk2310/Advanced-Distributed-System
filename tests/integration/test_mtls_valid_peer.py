from dataclasses import replace

import pytest

from distsys.crdt_client import CrdtClient
from distsys.node import DistributedNode
from tests.integration.cluster_helpers import cluster_settings
from tests.integration.tls_helpers import client_context, generate_dev_certs


@pytest.mark.asyncio
async def test_valid_mtls_crdt_client_succeeds(unused_tcp_port, tmp_path):
    certs = generate_dev_certs(tmp_path)
    settings = replace(
        cluster_settings(node_id="node-0", port=unused_tcp_port),
        crdt_enabled=True,
        crdt_replication_factor=1,
        persistence_enabled=False,
        etcd_enabled=False,
        tls_enabled=True,
        mtls_required=True,
        tls_ca_file=str(certs / "ca" / "ca.crt"),
        tls_cert_file=str(certs / "node-0" / "node.crt"),
        tls_key_file=str(certs / "node-0" / "node.key"),
    )
    node = DistributedNode(settings)
    await node.start()
    try:
        client = CrdtClient(
            port=unused_tcp_port,
            timeout_seconds=2.0,
            ssl_context=client_context(certs, "crdt-client"),
            server_hostname="node-0",
        )
        result = await client.increment("secure.counter")
        assert result.value == 1
    finally:
        await node.stop()
