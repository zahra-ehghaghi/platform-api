# Infrastructure bootstrap

Everything Platform API and this project's demo assume already exists (see
the main `README.md`'s **Prerequisites** section) is provisioned by
`bootstrap.sh`: a local `kind` cluster, ingress-nginx, ArgoCD, PostgreSQL,
Backstage, and `kube-prometheus-stack` (Prometheus + Grafana).

## Why this exists

Every component and every setting here (e.g.
`serviceMonitorSelectorNilUsesHelmValues=false`, the `ingress-ready=true`
node label, the `kind` port mappings for 80/443) was discovered by hand
while building this project, usually while debugging why something silently
wasn't working. Capturing it as a script means the whole environment is
reproducible from a clean machine, not just something that happens to exist
on one laptop.

## Prerequisites

`docker`, `kind`, `kubectl`, `helm` installed locally.

## Secrets are never hardcoded

`bootstrap.sh` reads `GITHUB_TOKEN`, `AUTH_GITHUB_CLIENT_ID`,
`AUTH_GITHUB_CLIENT_SECRET`, and `BACKSTAGE_DB_PASSWORD` from environment
variables — never from a file that could be committed. Copy the example env
file and fill in real values:

```bash
cp infra/.env.infra.example infra/.env.infra
# edit infra/.env.infra with real values — this file is gitignored
```

Then run:

```bash
set -a; source infra/.env.infra; set +a
./infra/bootstrap.sh
```

The script is idempotent — every step checks for an existing resource before
creating one, so re-running it after a partial failure or to pick up a
config change is safe.

## What it does, in order

1. Creates a `kind` cluster with ports 80/443 mapped to the host and the
   `ingress-ready=true` node label ingress-nginx's kind provider manifest
   expects.
2. Installs ingress-nginx using the kind-specific provider manifest, and
   waits for the controller pod to be ready before continuing.
3. Applies a CoreDNS configmap that hardcodes IP resolution for
   `github.com` and the GitHub Actions hosts services in this cluster need
   to reach (`api.github.com`, `codeload.github.com`,
   `objects.githubusercontent.com`, etc). This works around environments
   where outbound DNS resolution to GitHub from inside the cluster is
   unreliable (e.g. behind a proxy) — the `reload` plugin in the Corefile
   picks up the change automatically, no CoreDNS restart required.
4. Installs ArgoCD via the `argo-helm` chart, exposed at `argocd.test.com`.
5. Installs PostgreSQL (Bitnami chart) as the database backing Backstage.
6. Deploys Backstage itself: a Kubernetes `Secret` holding the sensitive
   values, a `ConfigMap` holding `app-config.production.yaml`, and the
   Backstage `Deployment`/`Service`/`Ingress`, exposed at `backstage.test.com`.
7. Installs `kube-prometheus-stack` (Prometheus Operator, Prometheus,
   Grafana, Alertmanager) into the `monitoring` namespace, with
   `serviceMonitorSelectorNilUsesHelmValues=false` and
   `ruleSelectorNilUsesHelmValues=false` — without these, `ServiceMonitor`
   and `PrometheusRule` resources created by services provisioned through
   Platform API are silently ignored.
8. Applies Ingresses for Prometheus and Grafana.

## After running

Add the printed hostnames to `/etc/hosts` (the script prints the exact
lines), then:

- ArgoCD: `https://argocd.test.com` — get the initial admin password with
  `kubectl -n argocd get secret argocd-initial-admin-secret -o jsonpath="{.data.password}" | base64 -d`
- Grafana: `http://grafana.test.com` — `admin` / `GRAFANA_ADMIN_PASSWORD`
  (default `admin123`)
- Prometheus: `http://prometheus.test.com`
- Backstage: `http://backstage.test.com`

## Known gaps

- **`coredns-configmap.yaml` hardcodes GitHub's IP addresses.** These IPs
  can and do change over time (GitHub does not guarantee them), so this is
  a pragmatic workaround for one environment's proxy/DNS constraints, not a
  portable solution. If GitHub connectivity from the cluster breaks after
  previously working, stale IPs here are a likely first place to check —
  compare against a fresh `dig github.com` from a machine with working
  DNS. A more robust fix would point the cluster at a working upstream
  DNS resolver or a proxy-aware `forward` target instead of pinning IPs.
- This script provisions infrastructure only. It does not run
  Platform API itself — see the main `README.md` for that.
