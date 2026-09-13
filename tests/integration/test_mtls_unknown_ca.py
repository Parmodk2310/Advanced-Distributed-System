import asyncio
import ssl
from dataclasses import replace

import pytest

from distsys.node import DistributedNode
from tests.integration.cluster_helpers import cluster_settings
from tests.integration.tls_helpers import client_context, generate_dev_certs


@pytest.mark.asyncio
async def test_unknown_ca_client_certificate_is_rejected(unused_tcp_port, tmp_path):
    certs = generate_dev_certs(tmp_path / "trusted")
    other = generate_dev_certs(tmp_path / "other")
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
        context = client_context(other, "crdt-client")
        with pytest.raises((ssl.SSLError, ConnectionError, OSError)):
            await asyncio.open_connection(
                "127.0.0.1",
                unused_tcp_port,
                ssl=context,
                server_hostname="node-0",
            )
    finally:
        await node.stop()


@pytest.mark.asyncio
async def test_missing_client_certificate_is_rejected_when_mtls_required(
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
        context = ssl.create_default_context(
            ssl.Purpose.SERVER_AUTH,
            cafile=str(certs / "ca" / "ca.crt"),
        )
        context.minimum_version = ssl.TLSVersion.TLSv1_3
        try:
            reader, writer = await asyncio.open_connection(
                "127.0.0.1",
                unused_tcp_port,
                ssl=context,
                server_hostname="node-0",
            )
        except (ssl.SSLError, ConnectionError, OSError):
            return
        try:
            writer.write(b"x")
            await writer.drain()
            data = await asyncio.wait_for(reader.read(1), timeout=0.5)
            assert data == b""
        except (ssl.SSLError, ConnectionError, OSError):
            pass
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except (ssl.SSLError, ConnectionError, OSError):
                pass
    finally:
        await node.stop()
