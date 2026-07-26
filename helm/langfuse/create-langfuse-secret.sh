#!/usr/bin/env bash
#
# Create the `langfuse-secrets` Kubernetes Secret consumed by helm/langfuse/values.yaml.
#
# WHY: no plaintext secret ever lands in git. values.yaml only references this
# Secret (secretKeyRef / existingSecret); the actual values are generated here at
# deploy time with `openssl rand -hex` (URL-safe hex → the Postgres/ClickHouse/
# Redis connection strings need no URL-encoding).
#
# IDEMPOTENT: if the Secret already exists it is left untouched, because the
# datastore passwords are baked into the PersistentVolumes on first init —
# regenerating them would lock Langfuse out of its own databases. To rotate,
# delete the release + PVCs + this Secret, then re-run.
#
# Usage:
#   ./helm/langfuse/create-langfuse-secret.sh
#   helm install langfuse langfuse/langfuse -n langfuse -f helm/langfuse/values.yaml

set -euo pipefail

NS="${LANGFUSE_NAMESPACE:-langfuse}"
SECRET="${LANGFUSE_SECRET_NAME:-langfuse-secrets}"

kubectl create namespace "$NS" --dry-run=client -o yaml | kubectl apply -f -

if kubectl get secret "$SECRET" -n "$NS" >/dev/null 2>&1; then
  echo "Secret '$SECRET' already exists in namespace '$NS' — leaving it untouched."
  echo "(To rotate: helm uninstall langfuse -n $NS && kubectl delete pvc --all -n $NS && kubectl delete secret $SECRET -n $NS, then re-run.)"
  exit 0
fi

kubectl create secret generic "$SECRET" -n "$NS" \
  --from-literal=nextauth-secret="$(openssl rand -hex 32)" \
  --from-literal=salt="$(openssl rand -hex 32)" \
  --from-literal=encryption-key="$(openssl rand -hex 32)" \
  --from-literal=init-project-public-key="pk-lf-$(cat /proc/sys/kernel/random/uuid)" \
  --from-literal=init-project-secret-key="sk-lf-$(cat /proc/sys/kernel/random/uuid)" \
  --from-literal=init-user-password="$(openssl rand -hex 16)" \
  --from-literal=postgres-password="$(openssl rand -hex 24)" \
  --from-literal=clickhouse-password="$(openssl rand -hex 24)" \
  --from-literal=redis-password="$(openssl rand -hex 24)" \
  --from-literal=minio-root-user="langfuse" \
  --from-literal=minio-root-password="$(openssl rand -hex 24)"

echo "Created Secret '$SECRET' in namespace '$NS'."
