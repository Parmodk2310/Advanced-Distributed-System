import os

# ============================================================
# DISTRIBUTED SYSTEM PROJECT
# Add Kubernetes, Helm and Terraform deployment files
# ============================================================

BASE_DIR = r"D:\Projects\distributed-system"


# ============================================================
# FILES TO ADD
# ============================================================

files = [
    # --------------------------------------------------------
    # Kubernetes
    # --------------------------------------------------------
    "k8s/base/namespace.yaml",
    "k8s/base/configmap.yaml",
    "k8s/base/secret.yaml",
    "k8s/base/service.yaml",
    "k8s/base/statefulset.yaml",
    "k8s/base/etcd.yaml",
    "k8s/base/prometheus.yaml",
    "k8s/base/ingress.yaml",
    "k8s/base/hpa.yaml",
    "k8s/base/kustomization.yaml",

    # --------------------------------------------------------
    # Helm
    # --------------------------------------------------------
    "helm/distributed-system/Chart.yaml",
    "helm/distributed-system/values.yaml",

    "helm/distributed-system/templates/statefulset.yaml",
    "helm/distributed-system/templates/service.yaml",
    "helm/distributed-system/templates/ingress.yaml",
    "helm/distributed-system/templates/hpa.yaml",
    "helm/distributed-system/templates/secret.yaml",
    "helm/distributed-system/templates/_helpers.tpl",

    # --------------------------------------------------------
    # Terraform - AWS
    # --------------------------------------------------------
    "terraform/aws/main.tf",
    "terraform/aws/variables.tf",

    # --------------------------------------------------------
    # Terraform - GCP
    # --------------------------------------------------------
    "terraform/gcp/main.tf",
    "terraform/gcp/variables.tf",
]


# ============================================================
# CREATE DIRECTORIES + FILES
# ============================================================

created = 0
skipped = 0

for relative_path in files:

    file_path = os.path.join(BASE_DIR, relative_path)

    # Create parent directory
    parent_dir = os.path.dirname(file_path)
    os.makedirs(parent_dir, exist_ok=True)

    # Do not overwrite existing files
    if os.path.exists(file_path):
        print(f"Skipped (already exists): {relative_path}")
        skipped += 1
        continue

    # Create empty file
    with open(file_path, "w", encoding="utf-8") as f:
        f.write("")

    print(f"Created: {relative_path}")
    created += 1


# ============================================================
# SUMMARY
# ============================================================

print()
print("Deployment infrastructure structure updated.")
print(f"Files created : {created}")
print(f"Files skipped : {skipped}")
print(f"Project path  : {BASE_DIR}")