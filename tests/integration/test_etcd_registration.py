from __future__ import annotations

import uuid

import pytest

from distsys.coordination.etcd_client import EtcdGatewayCoordinationClient
from distsys.coordination.models import CoordinationMember
from tests.integration.etcd_helpers import require_etcd_integration


@pytest.mark.asyncio
@pytest.mark.etcd
async def test_real_etcd_member_registration_and_discovery():
    endpoints = require_etcd_integration()
    namespace = f"/distsys/test/{uuid.uuid4().hex}"
    client = EtcdGatewayCoordinationClient(endpoints, namespace=namespace)
    await client.connect()
    try:
        member = CoordinationMember(
            node_id="node-test",
            node_uuid=str(uuid.uuid4()),
            host="127.0.0.1",
            port=18999,
            membership_incarnation=1,
            protocol_version=5,
            release="0.5.0",
            tls_required=True,
        )
        lease = await client.grant_lease(5)
        await client.put_node_metadata(member)
        await client.register_member(member, lease)
        discovered = await client.discover_members()
        assert discovered == (member,)
    finally:
        await client.close()
