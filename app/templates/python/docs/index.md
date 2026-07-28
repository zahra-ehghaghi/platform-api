# ${{values.app_name}}

A Python/Flask service provisioned via Platform API, deployed to the
`${{values.app_env}}` environment.

## Architecture

This service follows the platform's standard golden path:

```
GitHub repository (this repo)
   │
   ├─ src/app.py           Flask application
   ├─ Dockerfile            Container build
   ├─ charts/${{values.app_name}}/    Helm chart (Deployment, Service,
   │                                   ServiceMonitor, PrometheusRule)
   └─ .github/workflows/    CI: build & push image
                             CD: bump image tag, commit (no manual sync)
                                   │
                                   ▼
                         ArgoCD Application (automated sync + selfHeal)
                                   │
                                   ▼
                    Kubernetes namespace: ${{values.app_env}}
```

Deployment is fully GitOps-driven: pushing to `src/**` on `main` triggers a
build, and ArgoCD picks up the resulting Helm values change automatically —
there is no manual `argocd sync` step anywhere in this repo's pipeline.

## API

| Endpoint | Method | Description |
|---|---|---|
| `/api/v1/info` | GET | Returns hostname, current time, environment, and app name |
| `/api/v1/healthz` | GET | Liveness/readiness check — returns `{"status": "up"}` |
| `/metrics` | GET | Prometheus metrics (request count, request duration histogram) |

## Deployment

This service is deployed to the `${{values.app_env}}` namespace and reachable
at:

```
http://${{values.app_name}}-${{values.app_env}}.test.com
```

To ship a change:

1. Push a commit touching `src/**` to `main`.
2. CI builds and pushes a new Docker image tagged with the short commit SHA.
3. CD updates `charts/${{values.app_name}}/values-${{values.app_env}}.yaml`
   with the new tag and commits it back to `main`.
4. ArgoCD detects the change and reconciles the cluster automatically —
   typically within a few minutes, depending on ArgoCD's polling interval.

No manual steps are required after the initial `git push`.

## Observability

- **Metrics**: exposed at `/metrics`, scraped automatically via the
  `ServiceMonitor` included in this service's Helm chart.
- **Dashboard**: request rate, error rate, and p95 latency for this service
  (and all others) are visible on the platform-wide *Platform Services
  Overview* Grafana dashboard.
- **Alerting**: a `PrometheusRule` fires `HighErrorRate` if the 5xx rate for
  this service exceeds 5% for more than 2 minutes.

## Runbook

**Service shows `ImagePullBackOff` right after creation.**
Expected and transient. New services are registered with ArgoCD before the
first CI/CD run has produced a real image — see [ADR 0003](https://github.com/zahra-ehghaghi/platform-api/blob/main/docs/adr/0003-accept-transient-imagepullbackoff.md)
("Accept a transient ImagePullBackOff instead of forcing
build-before-provision ordering") in the Platform API repository. This
resolves itself automatically once the first push to `src/**` completes its
CI/CD run (a few minutes).

**Service shows `ImagePullBackOff` and does *not* resolve after several minutes.**
Check whether the initial CI/CD run actually succeeded:

```bash
# From this repository:
gh run list --workflow=${{values.app_name}}-cicd.yaml
```

If the CI job failed (commonly a bad `Dockerfile` or a failing
`docker/build-push-action` step), fix the underlying issue and push again —
ArgoCD will pick up the corrected tag automatically once CI/CD succeeds.

**`HighErrorRate` alert firing.**
Check recent logs for the failing pod:

```bash
kubectl logs -n ${{values.app_env}} -l app.kubernetes.io/instance=${{values.app_name}} --tail=100
```

Cross-reference with the *Platform Services Overview* Grafana dashboard to
confirm which endpoint is producing 5xx responses, and check
`kubectl describe pod` for the affected pod if it's crash-looping rather
than returning application-level errors.

**Namespace-level resource pressure (`ResourceQuota` exceeded).**
This service shares its namespace's `ResourceQuota` with every other service
in the same environment. If pod scheduling fails due to quota, check current
usage:

```bash
kubectl describe resourcequota -n ${{values.app_env}}
```

