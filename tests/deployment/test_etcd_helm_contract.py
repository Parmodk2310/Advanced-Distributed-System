from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def read(p):
    return (ROOT / p).read_text()


def test_three_member_etcd_quorum_contract():
    values = read("deploy/helm/etcd/values.yaml")
    sts = read("deploy/helm/etcd/templates/statefulset.yaml")
    pdb = read("deploy/helm/etcd/templates/pdb.yaml")
    services = read("deploy/helm/etcd/templates/services.yaml")
    assert "replicaCount: 3" in values
    assert "replicas: 3" in sts
    assert "podManagementPolicy: Parallel" in sts
    assert "--initial-cluster=" in sts
    assert "--listen-peer-urls" in sts and "--listen-client-urls" in sts
    assert "volumeClaimTemplates" in sts
    assert "persistentVolumeClaimRetentionPolicy" in sts
    assert "minAvailable: 2" in pdb
    assert "clusterIP: None" in services
    assert "peerPort: 2380" in values and "clientPort: 2379" in values
    assert "@{{" not in sts


def test_etcd_image_is_digest_pinned_and_storage_is_gp3():
    values = read("deploy/helm/etcd/values.yaml")
    storage = read("deploy/helm/etcd/templates/storageclass.yaml")
    assert "sha256:0934690612905554eb61ddefb9faaaecb47c2f6931dbb453e694358092ee8990" in values
    assert "ebs.csi.aws.com" in values
    assert "WaitForFirstConsumer" in storage
    assert 'tagSpecification_1: "Phase=7"' in storage
