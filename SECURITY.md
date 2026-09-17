# Security Policy

## Supported versions

Security fixes target the current `main` branch and the latest formal release.

| Version | Security support |
| --- | --- |
| `main` | Supported |
| latest formal release | Supported |
| older development tags | Best effort only |

Historical tags are engineering checkpoints and may not receive backported
security fixes.

## Reporting a vulnerability

Do **not** publish an undisclosed vulnerability, exploit, credential, private
key, cloud identifier, or sensitive reproduction detail in a public issue.

Preferred path:

1. Open the repository **Security** tab.
2. Use **Report a vulnerability** / private vulnerability reporting if enabled.
3. Include the affected commit or release, reproduction steps, impact, and any
   suggested mitigation.

If private vulnerability reporting is unavailable, open a minimal public issue
asking the maintainer to establish a private reporting channel. Do not include
exploit details.

## What to include

A useful report contains:

- affected commit, tag, image digest, or workflow,
- component and file path,
- preconditions,
- minimal reproduction,
- expected vs. actual behavior,
- impact,
- whether credentials or cloud resources are involved,
- whether the issue is already public,
- suggested mitigation if known.

## Response goals

This is an individual portfolio/open-source project rather than a commercial
security response organization. The maintainer will still try to:

- acknowledge a valid private report promptly,
- reproduce and classify the issue,
- avoid publishing exploit details before a fix is available,
- add a regression test where practical,
- rerun relevant quality/security gates,
- document the fix in the changelog or release notes when appropriate.

No guaranteed response-time SLA is offered.

## Security model

The repository includes:

- TLS 1.3 secure profile,
- mutual TLS between supported peers,
- logical node identity verification against certificate SANs,
- non-root container execution,
- Kubernetes security policies,
- ephemeral local TLS material,
- Gitleaks secret scanning,
- Trivy image vulnerability scanning,
- SPDX SBOM generation,
- keyless signing of immutable image digests,
- GitHub OIDC for AWS access,
- no long-lived AWS access keys in the Phase 7 workflow design,
- explicitly gated AWS apply,
- bounded temporary cloud demonstrations,
- teardown and residual-resource verification.

These controls reduce risk; they do not make the system universally secure.

## Security non-claims

This project does **not** claim:

- formal cryptographic verification,
- Byzantine fault tolerance,
- resistance to a fully compromised host/root account,
- hardware-backed key protection,
- zero-day immunity,
- complete dependency-vulnerability elimination,
- arbitrary untrusted multi-tenant isolation,
- internet-scale DDoS protection,
- a production security SLA.

## Secrets and credentials

Never commit:

- AWS access keys or session credentials,
- private keys,
- kubeconfig files,
- Terraform state,
- `.tfplan` files containing sensitive values,
- real `.env` secrets,
- GitHub tokens,
- cloud account identifiers that are not intentionally public,
- personally identifying infrastructure metadata.

Use placeholders in committed examples and documentation.

The Phase 7 local workflow creates temporary TLS material and removes it during
cleanup. AWS authentication is designed around GitHub OIDC instead of static
long-lived cloud keys.

## Cloud safety

Normal development and Phase 7A verification must not create AWS resources.

A cloud demonstration should require:

- explicit enablement,
- reviewed Terraform plan,
- exact commit/digest pinning,
- protected environment approval,
- cost boundary,
- restricted API CIDRs,
- explicit expiration metadata,
- teardown immediately after evidence capture,
- residual-resource verification.

The verified Phase 7 AWS demonstration was temporary and was destroyed after
testing.

## Dependency and image security

Before publishing a release:

```bash
make quality
make phase7-release-gate
```

Also verify the relevant GitHub Actions security/image workflows are green.

The release-blocking vulnerability policy is defined by the repository's CI and
release-gate configuration; this document does not silently weaken those rules.

## License scope

The repository's Apache-2.0 license applies to work contributed under this
repository.

It does **not** relicense Python, Kubernetes, etcd, Docker, Terraform,
Prometheus, Grafana, OpenTelemetry, AWS services, or other third-party
dependencies.
