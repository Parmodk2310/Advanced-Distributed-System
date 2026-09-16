from distsys.cluster.service import ClusterService
from distsys.utils.config import Settings


async def _execute_local(name, payload, deadline):  # pragma: no cover - construction helper
    return None


def test_cluster_member_uses_advertised_host_without_changing_bind_host() -> None:
    settings = Settings(
        node_id="node-0",
        host="0.0.0.0",
        advertise_host="node-0.headless",
        cluster_enabled=True,
    )
    service = ClusterService(settings=settings, bound_port=8000, execute_local=_execute_local)

    assert settings.host == "0.0.0.0"
    assert service.local_member.host == "node-0.headless"
