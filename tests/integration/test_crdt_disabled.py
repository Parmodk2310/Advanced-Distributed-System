import pytest

from distsys.crdt_client import CrdtClient, RemoteCrdtError
from distsys.node import DistributedNode
from distsys.proto import messages_pb2
from distsys.utils.config import Settings


@pytest.mark.asyncio
async def test_crdt_messages_are_rejected_when_phase_four_is_disabled(unused_tcp_port):
    node = DistributedNode(Settings(host="127.0.0.1", port=unused_tcp_port))
    try:
        await node.start()
        assert node.crdt_service is None
        with pytest.raises(RemoteCrdtError) as exc:
            await CrdtClient(port=unused_tcp_port, timeout_seconds=1).increment("disabled")
        assert exc.value.code == messages_pb2.INVALID_REQUEST
    finally:
        await node.stop()
