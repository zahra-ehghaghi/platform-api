# Platform API

A self-service Internal Developer Platform (IDP) backend that provisions
services end-to-end: GitHub repository, CI/CD pipeline, a multi-tenant
Kubernetes namespace, and a GitOps-managed deployment via ArgoCD — triggered
by a single API call.

Built as the next evolution of a Backstage-based developer portal, this
project moves provisioning logic **out of** Backstage templates and CI/CD
scripts and **into** a standalone, independently testable service — the same
pattern used by internal platform teams at larger engineering orgs.

## Why this exists

The original setup used a Backstage Software Template that called
`publish:github` directly, and a GitHub Actions workflow that shelled out to
the `argocd` CLI to register and sync applications. That worked, but it
tightly coupled three concerns — developer portal, CI/CD, and deployment
orchestration — into scripts that were hard to test, hard to reuse outside
Backstage, and required a self-hosted runner with direct cluster network
access.

Platform API replaces that with a single HTTP endpoint:

```
POST /services
{
  "name": "payment-service",
  "language": "python",
  "environment": "dev"
}
```

Everything downstream — repo creation, template files, namespace
provisioning, tenant isolation, ArgoCD registration — is handled by the API
itself, callable from Backstage, a CLI, or any other CI/CD system.

## Architecture

```
Developer
   │
   ▼
Backstage  ──or──  curl / any client
   │
   ▼
Platform API (FastAPI)
   │
   ├──▶ GitHub API ────▶ new repository + templated source (single atomic commit)
   │
   ├──▶ Kubernetes API ▶ Namespace + ResourceQuota + LimitRange
   │                     + NetworkPolicy + ServiceAccount + Role + RoleBinding
   │
   └──▶ ArgoCD API ────▶ Application (automated sync + selfHeal)
                              │
                              ▼
                         Kubernetes (GitOps, tenant-isolated)
```

Once the repository exists, a GitHub Actions workflow in the generated repo
handles the ongoing loop:

```
push to src/**
   │
   ▼
CI: build & push Docker image (tagged with short commit SHA)
   │
   ▼
CD: bump image.tag in the Helm values file, commit
   │
   ▼
ArgoCD (automated + selfHeal) detects the Git change and reconciles the cluster
```

Note there's no `argocd sync` call anywhere in the CI/CD workflow. ArgoCD
watches the repo and self-heals — the pipeline's only job is to get the
correct image tag into Git.

## Design decisions

**Single API call, not a chain of Backstage actions.**
Provisioning logic lives in one place, testable independently of Backstage,
and reusable by any caller.

**Atomic commits via the Git Tree API, not one commit per file.**
Early iterations pushed one commit per template file using
`repo.create_file()`. That caused the CI/CD job's own commit-back step to
collide with the last few template-push commits (`non-fast-forward` push
rejections), because GitHub Actions checks out the exact SHA that triggered
the workflow while the API kept pushing behind it. Switching to the Git Tree
API (build blobs → tree → single commit) makes repository creation atomic and
removes the race entirely.

**GitOps sync is fully automated (`automated: {prune: true, selfHeal: true}`), not conditional on environment.**
No manual `argocd app sync` step, and no environment-based branching between
"auto for dev, manual for prod." Git is the single source of truth for every
environment; ArgoCD reconciles on its own schedule and self-heals any manual
drift.

**No self-hosted runner required.**
Because ArgoCD reconciles automatically, the CD job never needs to reach the
cluster's internal network — it only edits a YAML file and pushes to GitHub.
That means `runs-on: ubuntu-latest` is sufficient; there's no dependency on a
self-hosted runner pod living inside the cluster.

**The Application is created before a real image exists — deliberately.**
This is the well-known GitOps "chicken-and-egg" problem: the Application
needs to be provisioned before CI/CD has ever produced a valid image tag.
Rather than trying to force an ordering (build first, then provision — which
reintroduces the coupling this project removes), the platform accepts a
transient `ImagePullBackOff` immediately after provisioning and relies on
`selfHeal` to converge automatically once the first CI/CD run completes.

**Namespace isolation is provisioned by the platform, not by ArgoCD's `CreateNamespace` flag.**
Earlier, namespaces were created implicitly by ArgoCD's `CreateNamespace=true`
sync option — which produces a bare namespace with no quota, no limits, no
network policy, and no scoped identity. The platform now creates the
namespace itself, before the Application is registered, and immediately
attaches the tenant-isolation primitives below. ArgoCD's `CreateNamespace`
option is kept only as a harmless no-op fallback.

**Least-privilege RBAC per namespace, not a shared default ServiceAccount.**
Each namespace gets its own `ServiceAccount` bound to a `Role` (not a
`ClusterRole`) that only grants `get/list/watch` on `pods`, `services`, and
`configmaps` — deliberately excluding `secrets` and any write verb. Scoping
to `Role`/`RoleBinding` instead of cluster-wide equivalents means a
credential obtained in `dev` has no authority in `prod`, verified directly
with `kubectl auth can-i --as=system:serviceaccount:...`.

**All provisioning steps are idempotent.**
Every Kubernetes/GitHub/ArgoCD client method checks for existence before
creating, so re-registering an existing repo, namespace, quota, policy, or
Application is a no-op rather than an error. This matters because multiple
services share the same `dev`/`prod` namespace — the tenant-isolation
resources are only created once, on the first service in that environment.

## What it does today

- `POST /services` — creates a GitHub repository from a language-specific
  template (currently Python/Flask), pushes Helm chart + Dockerfile +
  starter app + CI/CD workflow in a single commit, provisions a tenant-isolated
  namespace, registers the repo with ArgoCD, and creates an auto-syncing
  Application scoped to that namespace.
- **Tenant isolation per namespace**, applied automatically and idempotently:
  - `ResourceQuota` — caps aggregate CPU/memory requests & limits and pod
    count for the whole namespace
  - `LimitRange` — default/min/max CPU & memory per container, so workloads
    that omit `resources:` don't go unbounded
  - `NetworkPolicy` — denies ingress by default; allows traffic only from
    pods in the same namespace and from `ingress-nginx`
  - `ServiceAccount` + `Role` + `RoleBinding` — least-privilege, namespace-scoped
    identity (read-only on pods/services/configmaps, no secrets access)
- Idempotent by design: re-registering an existing repo, namespace, or
  Application is a no-op rather than an error.

## Tech stack

- **FastAPI** — API framework, request validation via Pydantic models/enums
- **PyGithub** — repository and Git Tree API operations
- **httpx** — ArgoCD REST API client (session auth, repository/application management)
- **kubernetes** (official Python client) — namespace, quota, limit range,
  network policy, and RBAC provisioning
- **ArgoCD** — GitOps continuous delivery
- **GitHub Actions** — per-service CI/CD (build/push image, bump Helm values)
- **Kubernetes (kind)** — target runtime

## Project structure

```
platform-api/
├── app/
│   ├── main.py                 # FastAPI app, router registration, /health
│   ├── core/
│   │   └── config.py           # Settings loaded from environment / .env
│   ├── models/
│   │   └── service.py          # Request/response schemas, Language & Environment enums
│   ├── clients/
│   │   ├── github_client.py    # Repo creation, atomic template push (Git Tree API)
│   │   ├── argocd_client.py    # Session auth, repo registration, Application lifecycle
│   │   └── k8s_client.py       # Namespace, ResourceQuota, LimitRange,
│   │                           # NetworkPolicy, ServiceAccount, Role, RoleBinding
│   ├── routers/
│   │   └── services.py         # POST /services orchestration
│   └── templates/
│       └── python/             # Flask service template: Helm chart, Dockerfile,
│                                # starter app, GitHub Actions workflow
├── requirements.txt
└── Dockerfile
```

## Running locally

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Create a `.env` file:

```
GITHUB_TOKEN=ghp_xxxxxxxxxxxx
GITHUB_ORG=your-org
ARGOCD_SERVER=argocd.yourdomain.com
ARGOCD_USERNAME=admin
ARGOCD_PASSWORD=your-argocd-password
DOCKERHUB_USERNAME=your-dockerhub-username
ARGOCD_VERIFY_SSL=false
```

Kubernetes access is picked up automatically: the client tries
`load_incluster_config()` first (for when the API runs inside the cluster)
and falls back to `~/.kube/config` for local development — no extra
configuration needed either way.

Run:

```bash
uvicorn app.main:app --reload --port 8000 --host 0.0.0.0
```

Interactive API docs at `http://localhost:8000/docs`.

Create a service:

```bash
curl -X POST http://localhost:8000/services \
  -H "Content-Type: application/json" \
  -d '{"name": "demo-service", "language": "python", "environment": "dev"}'
```

Verify tenant isolation for a namespace:

```bash
kubectl get resourcequota,limitrange,networkpolicy,serviceaccount,role,rolebinding -n dev

# Confirm least-privilege RBAC:
kubectl auth can-i list pods -n dev --as=system:serviceaccount:dev:platform-app      # yes
kubectl auth can-i list secrets -n dev --as=system:serviceaccount:dev:platform-app   # no
kubectl auth can-i delete pods -n dev --as=system:serviceaccount:dev:platform-app    # no
kubectl auth can-i list pods -n prod --as=system:serviceaccount:dev:platform-app     # no
```

## Known limitations / next steps

This is an active work-in-progress platform, not a finished product. Current
gaps, tracked as the next iteration of this project:

- **NetworkPolicy enforcement depends on the CNI.** Policies are created via
  the Kubernetes API regardless of cluster, but enforcement requires a
  policy-aware CNI (e.g. Calico, Cilium). The default `kind` cluster used for
  local development runs `kindnet`, which does not enforce `NetworkPolicy` —
  the policies are correctly defined but not actively enforced in this
  environment. Egress is intentionally left unrestricted for now; only
  ingress is controlled.
- **Namespaces are shared per environment**, not per service (`dev` and
  `prod`, not `payment-service-dev`). Tenant-isolation resources are created
  once per namespace and shared by every service in that environment — a
  design trade-off, not an oversight, worth revisiting if per-service
  isolation becomes a requirement.
- **Secrets management** — GitHub/ArgoCD/DockerHub credentials are still
  environment-variable based; no Vault integration yet.
- **Observability** — no automatic `ServiceMonitor` or dashboard provisioning
  per service yet.
- **Single language template** — only Python/Flask exists; Node/Go templates
  are planned.
- **No background task / async status** — `POST /services` runs the full
  provisioning flow synchronously; a long-running GitHub/ArgoCD/Kubernetes
  API delay blocks the response.

## Background

This project is part of a broader Internal Developer Platform build,
originally scaffolded with [Backstage](https://backstage.io/). The full
context — including the Backstage templates, Helm charts, and the reasoning
behind moving CI/CD orchestration out of Backstage — is documented in the
companion repository: `backstage-software-templates`.

