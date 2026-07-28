# ADR 0001: Move provisioning logic out of Backstage/CI into a standalone Platform API

## Status
Accepted

## Context
The original setup provisioned new services entirely through a Backstage
Software Template: a `publish:github` scaffolder action created the
repository, and the generated GitHub Actions workflow shelled out to the
`argocd` CLI (`argocd repo add`, `argocd app create`, `argocd app sync`) to
register the service with ArgoCD. This worked end-to-end, but coupled three
distinct concerns into one execution path:

- **Developer portal** (Backstage's scaffolder templating)
- **CI/CD** (GitHub Actions build/push)
- **Deployment orchestration** (ArgoCD repo/application registration)

This coupling had concrete costs:

- The provisioning logic (repo creation, ArgoCD registration) was only
  reachable through a Backstage template run — it couldn't be tested in
  isolation, called from a script, or reused by any other caller (a CLI, a
  Slack bot, another CI system).
- Registering the ArgoCD Application required a runner with direct network
  access to the cluster's internal services, which meant a self-hosted
  GitHub Actions runner had to live inside the cluster — an extra piece of
  infrastructure to operate and keep healthy.
- Provisioning logic was duplicated across every generated
  `.github/workflows/cicd.yaml` file rather than living in one place.

## Decision
Extract all provisioning logic into a standalone FastAPI service
(`platform-api`) exposing a single endpoint, `POST /services`, that performs
the full provisioning flow: GitHub repository creation, template file push,
namespace/tenant-isolation setup, and ArgoCD Application registration.

Backstage (or any other caller — a CLI, `curl`, another automation) becomes a
thin client that calls this API instead of performing the provisioning steps
itself.

## Consequences

**Positive:**
- Provisioning logic is testable and runnable independently of Backstage.
- A single source of truth for how a service gets provisioned, instead of
  logic duplicated across every generated CI/CD workflow.
- Opens the door to other callers (CLI, chatops, a future self-service UI)
  without touching the core provisioning logic.

**Negative / trade-offs:**
- Introduces a new service to operate, secure, and keep available — if
  Platform API is down, no new services can be provisioned (previously,
  Backstage itself failing was the only single point of failure).
- `POST /services` currently runs the full flow synchronously; a slow
  GitHub/ArgoCD/Kubernetes API call blocks the HTTP response. Acceptable for
  the current scale, but worth revisiting with a background task / async
  status pattern if provisioning volume grows.
- Secrets (GitHub token, ArgoCD credentials) now need to be available to
  Platform API specifically, rather than scattered across CI/CD workflow
  secrets — a net improvement for secret sprawl, but it does concentrate
  more privilege in one service.
