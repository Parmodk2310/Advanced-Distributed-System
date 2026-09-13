import asyncio
from dataclasses import replace

import pytest

from distsys.cluster.codec import encode_join_request
from distsys.cluster.member import ClusterMember, MemberStatus
from distsys.node import DistributedNode
from distsys.protocol.framing import encode_frame, read_message
from distsys.protocol.message import Message, MessageType
from tests.integration.cluster_helpers import cluster_settings
from tests.integration.tls_helpers import client_context, generate_dev_certs


@pytest.mark.asyncio
async def test_valid_ca_certificate_cannot_impersonate_another_node(
    unused_tcp_port,
    tmp_path,
):
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
        reader, writer = await asyncio.open_connection(
            "127.0.0.1",
            unused_tcp_port,
            ssl=client_context(certs, "node-2"),
            server_hostname="node-0",
        )
        joining = ClusterMember(
            "node-1",
            "127.0.0.1",
            unused_tcp_port + 1,
            MemberStatus.ALIVE,
            1,
        )
        message = Message.new_request(
            sender_id="node-1",
            msg_type=MessageType.JOIN_REQUEST,
            payload=encode_join_request(joining),
        )
        writer.write(encode_frame(message))
        await writer.drain()
        accepted = False
        try:
            await asyncio.wait_for(read_message(reader), timeout=0.5)
            accepted = True
        except (asyncio.IncompleteReadError, ConnectionError, TimeoutError):
            pass
        finally:
            writer.close()
            await writer.wait_closed()

        assert accepted is False
        assert node.cluster_service is not None
        snapshot = await node.cluster_service.membership.snapshot()
        assert {member.node_id for member in snapshot} == {"node-0"}
    finally:
        await node.stop()
