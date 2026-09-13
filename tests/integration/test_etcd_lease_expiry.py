from __future__ import annotations

import asyncio
import uuid

import pytest

from distsys.coordination.etcd_client import EtcdGatewayCoordinationClient
from distsys.coordination.models import CoordinationMember
from tests.integration.etcd_helpers import require_etcd_integration


@pytest.mark.asyncio
@pytest.mark.etcd
async def test_real_etcd_lease_expiry_removes_member_registration():
    endpoints = require_etcd_integration()
    namespace = f"/distsys/test/{uuid.uuid4().hex}"
    client = EtcdGatewayCoordinationClient(endpoints, namespace=namespace)
    await client.connect()
    try:
        member = CoordinationMember(
            node_id="node-expiring",
            node_uuid=str(uuid.uuid4()),
            host="127.0.0.1",
            port=18998,
            membership_incarnation=1,
            protocol_version=5,
            release="0.5.0",
            tls_required=True,
        )
        lease = await client.grant_lease(2)
        await client.register_member(member, lease)
        assert await client.discover_members() == (member,)

        loop = asyncio.get_running_loop()
        deadline = loop.time() + 6.0
        while loop.time() < deadline:
            if not await client.discover_members():
                break
            await asyncio.sleep(0.2)
        assert await client.discover_members() == ()
    finally:
        await client.close()
