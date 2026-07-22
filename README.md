# Platform API

A self-service Internal Developer Platform (IDP) backend that provisions
services end-to-end: GitHub repository, CI/CD pipeline, and a GitOps-managed
Kubernetes deployment via ArgoCD — triggered by a single API call.

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

Everything downstream — repo creation, template files, ArgoCD registration —
is handled by the API itself, callable from Backstage, a CLI, or any other
CI/CD system.

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
   ├──▶ GitHub API ──▶ new repository + templated source (single atomic commit)
   │
   └──▶ ArgoCD API ──▶ Application (automated sync + selfHeal)
                              │
                              ▼
                         Kubernetes (GitOps)
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

## What it does today

- `POST /services` — creates a GitHub repository from a language-specific
  template (currently Python/Flask), pushes Helm chart + Dockerfile +
  starter app + CI/CD workflow in a single commit, registers the repo with
  ArgoCD, and creates an auto-syncing Application scoped to the requested
  namespace.
- Idempotent by design: re-registering an existing repo or Application is a
  no-op rather than an error.

## Tech stack

- **FastAPI** — API framework, request validation via Pydantic models/enums
- **PyGithub** — repository and Git Tree API operations
- **httpx** — ArgoCD REST API client (session auth, repository/application management)
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
│   │   └── argocd_client.py    # Session auth, repo registration, Application lifecycle
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

## Known limitations / next steps

This is an active work-in-progress platform, not a finished product. Current
gaps, tracked as the next iteration of this project:

- **Multi-tenancy** — namespaces are created via ArgoCD's `CreateNamespace`
  option with no `ResourceQuota`, `LimitRange`, or `NetworkPolicy` applied yet.
- **Secrets management** — GitHub/ArgoCD/DockerHub credentials are still
  environment-variable based; no Vault integration yet.
- **Observability** — no automatic `ServiceMonitor` or dashboard provisioning
  per service yet.
- **Single language template** — only Python/Flask exists; Node/Go templates
  are planned.
- **No background task / async status** — `POST /services` runs the full
  provisioning flow synchronously; a long-running GitHub/ArgoCD API delay
  blocks the response.

## Background

This project is part of a broader Internal Developer Platform build,
originally scaffolded with [Backstage](https://backstage.io/). The full
context — including the Backstage templates, Helm charts, and the reasoning
behind moving CI/CD orchestration out of Backstage — is documented in the
companion repository: `backstage-software-templates`.

