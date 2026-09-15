# Phase 7 security and secrets

The runtime image is non-root, uses a read-only root filesystem, drops Linux capabilities, and uses RuntimeDefault seccomp. Kubernetes Services remain internal in committed values. Local mTLS certificates are generated under `.phase7/tls`, applied directly to a Secret, never printed, and removed by cleanup.

Do not commit kubeconfig, private keys, Terraform state/plans, AWS identifiers, or credentials. GitHub-to-AWS access uses OIDC and a protected `phase7-aws-demo` environment. Rotate local certificates by deleting the cluster and rerunning the release gate. Cloud secrets require an external secret manager before any long-lived deployment.
