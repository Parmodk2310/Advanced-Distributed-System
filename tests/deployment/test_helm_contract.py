from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def read(p):
    return (ROOT / p).read_text()


def test_application_chart_is_three_node_digest_capable_and_secure():
    values = read("deploy/helm/distributed-system/values.yaml")
    helpers = read("deploy/helm/distributed-system/templates/_helpers.tpl")
    sts = read("deploy/helm/distributed-system/templates/statefulset.yaml")
    cfg = read("deploy/helm/distributed-system/templates/configmap.yaml")
    assert "replicaCount: 3" in values
    assert "image.digest is required in release mode" in helpers
    assert 'NODE_HOST: "0.0.0.0"' in cfg
    assert "NODE_ADVERTISE_HOST" in sts
    assert "runAsNonRoot: true" in sts
    assert 'drop: ["ALL"]' in sts
    assert "readOnlyRootFilesystem: true" in sts
    assert "persistentVolumeClaimRetentionPolicy" in sts
    assert "whenDeleted: Delete" in sts
    assert "startupProbe" in sts and "readinessProbe" in sts and "livenessProbe" in sts


def test_eks_profile_uses_cloud_etcd_and_gp3_class():
    eks = read("deploy/helm/distributed-system/values-eks.yaml")
    assert "http://phase7-etcd:2379" in eks
    assert "storageClass: phase7-gp3" in eks
    assert "releaseMode: true" in eks


def test_application_replicas_are_spread_across_kubernetes_hosts():
    sts = read("deploy/helm/distributed-system/templates/statefulset.yaml")

    assert "topologySpreadConstraints:" in sts
    assert "maxSkew: 1" in sts
    assert "topologyKey: kubernetes.io/hostname" in sts
    assert "whenUnsatisfiable: ScheduleAnyway" in sts
    assert "whenUnsatisfiable: DoNotSchedule" not in sts
    assert "labelSelector:" in sts
