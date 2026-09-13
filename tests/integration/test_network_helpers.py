from tests.integration.cluster_helpers import cluster_settings


def test_cluster_settings_use_stable_local_probe_budgets():
    settings = cluster_settings(node_id="node-0", port=21999)
    assert settings.cluster_ping_timeout_seconds == 0.25
    assert settings.cluster_indirect_timeout_seconds == 0.25
