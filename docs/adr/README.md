# Architecture Decision Records

This directory records the significant architectural decisions made while
building Platform API, using the lightweight [Nygard ADR
format](https://cognitect.com/blog/2011/11/15/documenting-architecture-decisions):
context, decision, consequences.

| ADR | Title |
|---|---|
| [0001](0001-standalone-platform-api.md) | Move provisioning logic out of Backstage/CI into a standalone Platform API |
| [0002](0002-automated-gitops-sync.md) | Fully automated ArgoCD sync policy, not conditional on environment |
| [0003](0003-accept-transient-imagepullbackoff.md) | Accept a transient ImagePullBackOff instead of forcing build-before-provision ordering |
