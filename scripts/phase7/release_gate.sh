#!/usr/bin/env bash
set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)/common.sh"

# common.sh makes PHASE7_IMAGE readonly. Export the selected value without
# reassigning it so child lifecycle scripts deploy the exact image built,
# scanned, and SBOM'd by this release gate.
export PHASE7_IMAGE

for required in docker kind kubectl helm openssl terraform; do
  phase7_require_command "$required"
done

phase7_prepare_work_dir

backup="$(mktemp -d)"

cleanup() {
  if [[ -d "$PHASE7_WORK_DIR/evidence" ]]; then
    cp "$PHASE7_WORK_DIR"/evidence/*.json \
      "$backup"/ 2>/dev/null || true
  fi

  rm -rf \
    "$PHASE7_REPO_ROOT/deploy/terraform/aws/.terraform"

  "$PHASE7_SCRIPT_DIR/cluster_down.sh"

  mkdir -p "$PHASE7_WORK_DIR/evidence"

  cp "$backup"/*.json \
    "$PHASE7_WORK_DIR/evidence"/ \
    2>/dev/null || true

  rm -rf "$backup"
}

trap cleanup EXIT INT TERM

cd "$PHASE7_REPO_ROOT"

mkdir -p \
  "$PHASE7_WORK_DIR/rendered" \
  "$PHASE7_WORK_DIR/evidence"

echo "=== Python / repository quality ==="

python -m pytest -q
python -m ruff check src tests scripts
python -m black --check src tests scripts
python -m mypy src/distsys
python -m compileall -q src scripts tests

echo "=== Source secret scan ==="

SOURCE_SCAN_DIR="$PHASE7_WORK_DIR/source-scan"
rm -rf "$SOURCE_SCAN_DIR"
mkdir -p "$SOURCE_SCAN_DIR"

while IFS= read -r -d '' file; do
  [[ -e "$file" ]] || continue

  mkdir -p \
    "$SOURCE_SCAN_DIR/$(dirname "$file")"

  cp -a \
    "$file" \
    "$SOURCE_SCAN_DIR/$file"
done < <(
  git ls-files \
    -z \
    -c \
    -o \
    --exclude-standard
)

docker run --rm \
  -v "$SOURCE_SCAN_DIR:/repo:ro" \
  ghcr.io/gitleaks/gitleaks:v8.30.1 \
  dir /repo \
  --redact \
  --no-banner

rm -rf "$SOURCE_SCAN_DIR"

echo "=== Immutable local OCI image ==="

docker build \
  --pull \
  --tag "$PHASE7_IMAGE" \
  .

test "$(
  docker inspect \
    --format '{{.Config.User}}' \
    "$PHASE7_IMAGE"
)" = "10001:10001"

docker run \
  --rm \
  --entrypoint python \
  "$PHASE7_IMAGE" \
  -c 'import distsys; print("import-ok")'

echo "=== Image vulnerability scan ==="

docker run --rm \
  -v /var/run/docker.sock:/var/run/docker.sock \
  aquasec/trivy:0.70.0 \
  image \
  --severity HIGH,CRITICAL \
  --exit-code 1 \
  --no-progress \
  "$PHASE7_IMAGE"

echo "=== SBOM ==="

docker run --rm \
  -v /var/run/docker.sock:/var/run/docker.sock \
  anchore/syft:v1.51.1 \
  "$PHASE7_IMAGE" \
  -o spdx-json \
  > "$PHASE7_WORK_DIR/evidence/sbom.spdx.json"

python -m json.tool \
  "$PHASE7_WORK_DIR/evidence/sbom.spdx.json" \
  >/dev/null

echo "=== Helm lint ==="

helm lint \
  deploy/helm/distributed-system \
  -f deploy/helm/distributed-system/values-kind.yaml

helm lint \
  deploy/helm/etcd \
  -f deploy/helm/etcd/values-eks.yaml

echo "=== Render Kubernetes manifests ==="

helm template \
  phase7 \
  deploy/helm/distributed-system \
  --namespace distsys \
  -f deploy/helm/distributed-system/values-kind.yaml \
  > "$PHASE7_WORK_DIR/rendered/app-kind.yaml"

helm template \
  phase7 \
  deploy/helm/distributed-system \
  --namespace distsys \
  -f deploy/helm/distributed-system/values-eks.yaml \
  --set-string image.repository=example.invalid/distsys-node \
  --set-string image.digest=sha256:0000000000000000000000000000000000000000000000000000000000000000 \
  > "$PHASE7_WORK_DIR/rendered/app-eks.yaml"

helm template \
  phase7-etcd \
  deploy/helm/etcd \
  --namespace distsys \
  -f deploy/helm/etcd/values-eks.yaml \
  > "$PHASE7_WORK_DIR/rendered/etcd-eks.yaml"

echo "=== Kubeconform ==="

docker run --rm \
  -v "$PHASE7_REPO_ROOT:/project:ro" \
  ghcr.io/yannh/kubeconform:v0.6.7 \
  -strict \
  -summary \
  /project/.phase7/rendered/app-kind.yaml \
  /project/.phase7/rendered/app-eks.yaml \
  /project/.phase7/rendered/etcd-eks.yaml

echo "=== Conftest policy ==="

docker run --rm \
  -v "$PHASE7_REPO_ROOT:/project:ro" \
  openpolicyagent/conftest:v0.58.0 \
  test \
  --namespace phase7.kubernetes \
  --policy /project/.github/policies \
  /project/.phase7/rendered

echo "=== Terraform static validation ==="

terraform \
  -chdir=deploy/terraform/aws \
  fmt -check -recursive

terraform \
  -chdir=deploy/terraform/aws \
  init \
  -backend=false \
  -input=false

terraform \
  -chdir=deploy/terraform/aws \
  validate

echo "=== Live kind deployment ==="

PHASE7_SKIP_BUILD=1 \
bash "$PHASE7_SCRIPT_DIR/cluster_up.sh"

PYTHONPATH="$PHASE7_REPO_ROOT/src" \
python "$PHASE7_SCRIPT_DIR/verify_cluster.py" \
  --output "$PHASE7_WORK_DIR/evidence/cluster.json"

echo "=== Persistence ==="

PYTHONPATH="$PHASE7_REPO_ROOT/src" \
python "$PHASE7_SCRIPT_DIR/verify_persistence.py" \
  --output "$PHASE7_WORK_DIR/evidence/persistence.json"

echo "=== Rollback ==="

bash "$PHASE7_SCRIPT_DIR/verify_rollback.sh"

printf '%s\n' \
  '{"schema_version":1,"phase7a_release_gate":"pass","aws_resources_created":false}' \
  > "$PHASE7_WORK_DIR/evidence/phase7-local-verification.json"

echo "Phase 7A release gate passed"
