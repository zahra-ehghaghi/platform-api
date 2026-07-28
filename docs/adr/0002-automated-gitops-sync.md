# ADR 0002: Fully automated ArgoCD sync policy, not conditional on environment

## Status
Accepted

## Context
The original CI/CD workflow synced ArgoCD manually: after committing an
updated image tag to the Helm values file, the `cd` job logged into ArgoCD
via the CLI and explicitly ran `argocd app sync` + `argocd app wait`. This
required the job to reach the cluster's internal ArgoCD API, which is why a
self-hosted runner was needed (see ADR 0001).

When designing the replacement, two options were considered:

1. **Automated sync only for `dev`, manual sync for `prod`** — a common
   pattern that keeps a human-triggered gate before production changes take
   effect.
2. **Automated sync for every environment**, with Git as the sole source of
   truth and no environment-based branching in the sync policy at all.

## Decision
Use `syncPolicy.automated: {prune: true, selfHeal: true}` unconditionally,
for every `Application` regardless of environment (`dev` or `prod`). There is
no environment check anywhere in `argocd_client.py` or the CI/CD template
that changes this behavior.

## Consequences

**Positive:**
- Simpler code: one code path instead of an environment-conditional branch
  in `ensure_app()`, and no `if environment == "prod"` logic to maintain or
  explain.
- No self-hosted runner is required anywhere in the pipeline — the CD job
  only edits a YAML file and pushes to GitHub; ArgoCD's own reconciliation
  loop picks up the change and applies it. This directly enabled switching
  `runs-on: self-hosted` to `runs-on: ubuntu-latest`.
- `selfHeal: true` means any manual `kubectl edit` drift in the cluster is
  automatically reverted to match Git — Git is unambiguously the single
  source of truth for every environment, not just `dev`.

**Negative / trade-offs:**
- There is no manual approval gate before a `prod` change goes live purely
  through ArgoCD's sync policy. In a real production setup, a gate would
  need to be enforced upstream of ArgoCD — e.g. a GitHub Environment
  protection rule or required review on the PR that changes the `prod`
  values file — rather than by holding back the sync itself.
- Because sync is automatic, a bad commit to a service's Git repository
  (e.g. an invalid image tag) reaches the cluster immediately, in every
  environment, with no built-in pause. This is an accepted trade-off for
  this project's current scope, not a claim that no gate is ever needed in a
  real production platform.
