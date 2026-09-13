import socket

import pytest

from distsys.client import DistributedClient
from distsys.node import DistributedNode
from distsys.utils.config import Settings
from tests.integration import network_hosts


def test_non_wsl_uses_loopback(monkeypatch):
    monkeypatch.setattr(network_hosts, "is_wsl", lambda: False)
    assert network_hosts.local_tcp_test_host() == "127.0.0.1"


def test_wsl_uses_routed_linux_address(monkeypatch):
    monkeypatch.setattr(network_hosts, "is_wsl", lambda: True)
    monkeypatch.setattr(network_hosts, "routed_ipv4_address", lambda: "172.31.9.7")
    assert network_hosts.local_tcp_test_host() == "172.31.9.7"


def test_selected_host_can_bind_tcp_listener():
    host = network_hosts.local_tcp_test_host()
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind((host, 0))
        assert sock.getsockname()[1] > 0
    finally:
        sock.close()


@pytest.mark.asyncio
async def test_routed_linux_address_supports_node_round_trip():
    host = network_hosts.routed_ipv4_address()
    node = DistributedNode(Settings(node_id="network-host-test", host=host, port=0))
    await node.start()
    try:
        assert node.is_running
        client = DistributedClient(host=host, port=node.bound_port)
        assert await client.request("echo", {"host": host}) == {"host": host}
    finally:
        await node.stop()
