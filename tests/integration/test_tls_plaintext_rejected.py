import asyncio
from dataclasses import replace

import pytest

from distsys.node import DistributedNode
from distsys.protocol.framing import encode_frame
from distsys.protocol.message import Message
from tests.integration.cluster_helpers import cluster_settings
from tests.integration.tls_helpers import generate_dev_certs


@pytest.mark.asyncio
async def test_plaintext_protocol_is_rejected_by_tls_listener(unused_tcp_port, tmp_path):
    certs = generate_dev_certs(tmp_path)
    settings = replace(
        cluster_settings(node_id="node-0", port=unused_tcp_port),
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
        reader, writer = await asyncio.open_connection("127.0.0.1", unused_tcp_port)
        writer.write(encode_frame(Message.new_request(sender_id="client", payload=b"")))
        await writer.drain()
        data = await asyncio.wait_for(reader.read(1), timeout=1.0)
        assert data == b""
        writer.close()
        await writer.wait_closed()
    finally:
        await node.stop()
