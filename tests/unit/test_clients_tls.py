import asyncio

import pytest

from distsys.client import DistributedClient
from distsys.crdt_client import CrdtClient


class DummyWriter:
    def is_closing(self):
        return False

    def close(self):
        pass

    async def wait_closed(self):
        pass


@pytest.mark.asyncio
async def test_distributed_client_passes_tls_context_and_hostname(monkeypatch):
    calls = []

    async def fake_open(host, port, **kwargs):
        calls.append((host, port, kwargs))
        return object(), DummyWriter()

    monkeypatch.setattr(asyncio, "open_connection", fake_open)
    client = DistributedClient(ssl_context=object(), server_hostname="node-0")
    await client.connect()
    assert calls[0][2]["ssl"] is client.ssl_context
    assert calls[0][2]["server_hostname"] == "node-0"


@pytest.mark.asyncio
async def test_crdt_client_passes_tls_context_and_hostname(monkeypatch):
    calls = []

    async def fake_open(host, port, **kwargs):
        calls.append((host, port, kwargs))
        raise RuntimeError("stop after connect arguments")

    monkeypatch.setattr(asyncio, "open_connection", fake_open)
    client = CrdtClient(ssl_context=object(), server_hostname="node-0")
    with pytest.raises(RuntimeError, match="stop after connect"):
        await client.read("k")
    assert calls[0][2]["ssl"] is client.ssl_context
    assert calls[0][2]["server_hostname"] == "node-0"
