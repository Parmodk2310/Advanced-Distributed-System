# Phase 7 security and secrets

- Runtime image: non-root UID/GID 10001.
- Pod filesystem: read-only root filesystem, dropped capabilities, RuntimeDefault seccomp.
- Local certificates: generated only under `.phase7/tls`; private keys mode 0600; never committed.
- Release images: digest pinned; no `latest` deployment.
- GitHub-to-AWS: OIDC short-lived credentials; no static AWS keys.
- Terraform state: remote encrypted S3 backend with locking prerequisite; state and plans never enter Git.
- EKS public API: `0.0.0.0/0` forbidden.
- External application endpoint: temporary only, created after private verification and removed before teardown.
- App-etcd traffic in this demo remains HTTP inside the cluster and is restricted by NetworkPolicy; etcd transport TLS is not claimed by this Phase 7 bundle.
