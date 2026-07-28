# ADR 0003: Accept a transient ImagePullBackOff instead of forcing build-before-provision ordering

## Status
Accepted

## Context
In the original Backstage-driven flow, the ArgoCD `Application` was only
created *after* a full CI/CD run had already built a real Docker image and
committed a valid tag to the Helm values file. The ordering was implicit:
repo created → CI/CD ran once → `values.yaml` updated with a real tag → CD
job called `argocd app create` + `sync`. Because of that ordering, the
`Application` never existed with an invalid image reference.

Moving `Application` creation into Platform API (ADR 0001) broke that
implicit ordering: `POST /services` now creates the GitHub repository,
pushes the initial commit (including the Helm chart with whatever
placeholder `image.tag` is baked into the template), and registers the
ArgoCD `Application` — all before the first CI/CD run has ever produced a
real image. This is the well-known GitOps "chicken-and-egg" problem: the
`Application` needs to exist to be useful, but a valid image doesn't exist
until after the first build, which itself only runs after the repository
(and therefore the `Application`) already exists.

Two options were considered:

1. **Force the old ordering back**: have Platform API wait for, or itself
   trigger, an initial build before registering the `Application`. This
   re-couples provisioning to CI/CD execution and reintroduces exactly the
   kind of cross-system dependency ADR 0001 removed.
2. **Accept the transient invalid state**: create the `Application`
   immediately with whatever tag is in the template, let it briefly show
   `ImagePullBackOff`, and rely on `selfHeal` (ADR 0002) to converge once the
   first CI/CD run pushes a real tag.

## Decision
Accept option 2. `ensure_app()` creates the `Application` immediately, with
no dependency on a prior build. The Helm chart template's placeholder
`image.tag` is expected to be invalid at the moment of provisioning; the
`Application`'s `automated.selfHeal` reconciles it automatically once the
initial `src/**` commit triggers the repo's own CI/CD workflow and produces
a real tag — typically within a few minutes.

## Consequences

**Positive:**
- Keeps Platform API's provisioning flow simple and free of any dependency
  on CI/CD timing or GitHub Actions execution — it doesn't need to poll,
  wait, or orchestrate a build.
- The system is self-healing by construction: no special-case code is
  needed to "fix" the tag later, because the same `selfHeal` mechanism used
  for drift correction handles this case for free.

**Negative / trade-offs:**
- Every newly provisioned service is briefly (typically a few minutes)
  visible in `ImagePullBackOff` immediately after creation. This is
  cosmetically unpolished if shown in a live demo without explanation, and
  would be confusing to a developer unfamiliar with why it happens.
- If a repository's CI/CD workflow fails on its first run (e.g. a bad
  Dockerfile), the `Application` stays in `ImagePullBackOff` indefinitely
  with no automatic alerting distinguishing "still converging" from
  "permanently broken." The `HighErrorRate` alert (see the observability
  work) does not cover this case, since a pod that never starts produces no
  HTTP metrics at all.
