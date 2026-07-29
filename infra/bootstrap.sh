#!/usr/bin/env bash
#
# Bootstraps the full local infrastructure this project runs against:
# kind cluster -> ingress-nginx -> ArgoCD -> PostgreSQL -> Backstage ->
# kube-prometheus-stack (Prometheus + Grafana) -> Ingresses.
#
# Prerequisites: docker, kind, kubectl, helm.
#
# Required environment variables (do NOT hardcode these anywhere — export
# them in your shell, or `set -a; source .env.infra; set +a` before running
# this script; see .env.infra.example):
#   GITHUB_TOKEN               - GitHub PAT with repo access, used by Backstage
#   AUTH_GITHUB_CLIENT_ID      - GitHub OAuth App client ID for Backstage login
#   AUTH_GITHUB_CLIENT_SECRET  - GitHub OAuth App client secret
#   BACKSTAGE_DB_PASSWORD      - password for the Backstage PostgreSQL user
#
# Usage:
#   set -a; source .env.infra; set +a
#   ./bootstrap.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLUSTER_NAME="${CLUSTER_NAME:-kind}"

required_vars=(GITHUB_TOKEN AUTH_GITHUB_CLIENT_ID AUTH_GITHUB_CLIENT_SECRET BACKSTAGE_DB_PASSWORD)
for var in "${required_vars[@]}"; do
  if [ -z "${!var:-}" ]; then
    echo "ERROR: required environment variable '$var' is not set." >&2
    echo "See infra/.env.infra.example for the full list." >&2
    exit 1
  fi
done

echo "==> [1/8] Creating kind cluster ('${CLUSTER_NAME}') if it doesn't exist"
if ! kind get clusters | grep -q "^${CLUSTER_NAME}$"; then
  kind create cluster --name "${CLUSTER_NAME}" --config "${SCRIPT_DIR}/kind-config.yaml"
else
  echo "    Cluster '${CLUSTER_NAME}' already exists, skipping."
fi

echo "==> [2/8] Installing ingress-nginx (kind provider manifest)"
kubectl apply -f https://raw.githubusercontent.com/kubernetes/ingress-nginx/main/deploy/static/provider/kind/deploy.yaml
kubectl wait --namespace ingress-nginx \
  --for=condition=ready pod \
  --selector=app.kubernetes.io/component=controller \
  --timeout=180s

echo "==> [3/8] Applying CoreDNS configmap (hardcoded GitHub host resolution)"
# Overrides DNS resolution for github.com and related GitHub Actions hosts
# with static IPs. This works around environments where the cluster's
# outbound DNS resolution to GitHub is unreliable (e.g. behind a proxy).
# The 'reload' plugin in the Corefile picks up this change automatically
# within ~30s, no CoreDNS pod restart needed.
kubectl apply -f "${SCRIPT_DIR}/manifests/coredns-configmap.yaml"

echo "==> [4/8] Installing ArgoCD"
helm repo add argo https://argoproj.github.io/argo-helm >/dev/null
helm repo update >/dev/null
helm upgrade --install argocd argo/argo-cd \
  -n argocd --create-namespace \
  -f "${SCRIPT_DIR}/values/argocd-values.yaml"

echo "==> [5/8] Installing PostgreSQL for Backstage"
helm repo add bitnami https://charts.bitnami.com/bitnami >/dev/null
helm repo update >/dev/null
helm upgrade --install backstage-db bitnami/postgresql \
  -n backstage --create-namespace \
  -f "${SCRIPT_DIR}/values/postgres-values.yaml" \
  --set global.postgresql.auth.postgresPassword="${BACKSTAGE_DB_PASSWORD}" \
  --set global.postgresql.auth.password="${BACKSTAGE_DB_PASSWORD}"

echo "==> [6/8] Deploying Backstage"
kubectl create secret generic backstage-secrets \
  -n backstage \
  --from-literal=GITHUB_TOKEN="${GITHUB_TOKEN}" \
  --from-literal=AUTH_GITHUB_CLIENT_ID="${AUTH_GITHUB_CLIENT_ID}" \
  --from-literal=AUTH_GITHUB_CLIENT_SECRET="${AUTH_GITHUB_CLIENT_SECRET}" \
  --from-literal=POSTGRES_PASSWORD="${BACKSTAGE_DB_PASSWORD}" \
  --dry-run=client -o yaml | kubectl apply -f -

kubectl create configmap backstage-app-config \
  --from-file=app-config.production.yaml="${SCRIPT_DIR}/app-config.production.yaml" \
  -n backstage \
  --dry-run=client -o yaml | kubectl apply -f -

kubectl apply -f "${SCRIPT_DIR}/manifests/backstage-k8s.yaml"

echo "==> [7/8] Installing kube-prometheus-stack (Prometheus + Grafana)"
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts >/dev/null
helm repo update >/dev/null
kubectl create namespace monitoring --dry-run=client -o yaml | kubectl apply -f -
helm upgrade --install kube-prometheus-stack prometheus-community/kube-prometheus-stack \
  --namespace monitoring \
  --set grafana.adminPassword="${GRAFANA_ADMIN_PASSWORD:-admin123}" \
  --set prometheus.prometheusSpec.serviceMonitorSelectorNilUsesHelmValues=false \
  --set prometheus.prometheusSpec.ruleSelectorNilUsesHelmValues=false

echo "==> [8/8] Applying ingresses (Prometheus, Grafana)"
kubectl apply -f "${SCRIPT_DIR}/manifests/prometheus-ingress.yaml"
kubectl apply -f "${SCRIPT_DIR}/manifests/grafana-ingress.yaml"

cat <<'DONE'

==> Bootstrap complete.

Add these to /etc/hosts if not already present (adjust the IP if not on
localhost):
  127.0.0.1 argocd.test.com
  127.0.0.1 grafana.test.com
  127.0.0.1 prometheus.test.com
  127.0.0.1 backstage.test.com

ArgoCD initial admin password:
  kubectl -n argocd get secret argocd-initial-admin-secret -o jsonpath="{.data.password}" | base64 -d

Grafana login: admin / (GRAFANA_ADMIN_PASSWORD, default admin123)
DONE
