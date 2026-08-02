# ADR 0004: Move secrets from environment variables to Vault (dev mode)

## Status
Accepted

## Context
Platform API originally read all sensitive values — the GitHub token, the
ArgoCD admin password, the Docker Hub username — directly from environment
variables sourced from a local `.env` file. This was simple and worked, but
had real drawbacks:

- Every secret Platform API needed lived in one flat file, with no
  distinction between "safe to have in a shell env" and "should be tightly
  controlled and rotated."
- If `.env` were ever accidentally committed, copied, or exposed (something
  that already happened once during this project with a GitHub token
  embedded directly in a `.git/config` remote URL), every credential the
  service used would be exposed at once, with no audit trail of who or what
  read them.
- There was no separation between *connection info* (how to reach the
  secret store) and the secrets themselves — rotating a credential meant
  editing `.env` and restarting the service, with no history of the change.

## Decision
Introduce HashiCorp Vault, running in **dev mode**, as the source of truth
for `github_token` and `argocd_password`. Platform API's `.env` file now
only contains `VAULT_ADDR` and `VAULT_TOKEN` — the connection info needed to
reach Vault — not the secrets themselves. A new `VaultClient`
(`app/clients/vault_client.py`) reads secrets from Vault's KV v2 engine
under a single path (`secret/platform-api`), with per-key caching so each
secret is only fetched once per process lifetime.

Both `GithubClient` and `ArgocdClient` were refactored so that fetching
their respective secret from Vault happens lazily — on first real use via a
cached property — rather than in `__init__`. This follows the same pattern
already established for the GitHub organization lookup (see the
lazy-initialization discussion in this project's test suite): a
module-level singleton is created as soon as its module is imported, so any
I/O performed directly in `__init__` (including a Vault read) would make
importing that module require a reachable Vault instance, breaking
testability.

Vault is exposed via an Ingress (`vault.test.com`), following the same
pattern already used for ArgoCD, Grafana, and Prometheus, rather than
requiring a `kubectl port-forward` for local development.

## Consequences

**Positive:**
- `.env` now holds only a Vault address and token — a single credential to
  protect and rotate, instead of every downstream secret individually.
- Secrets are centralized in one place (Vault) rather than duplicated
  across `.env` files on every machine that runs Platform API.
- The lazy-initialization pattern applied here keeps the test suite
  network-free: tests mock `vault_client.get_secret` directly, the same way
  they already mocked `Github` and `httpx`.
- Sets up a clear migration path to a non-dev Vault deployment later,
  without changing any application code — only `VAULT_ADDR`/`VAULT_TOKEN`
  and the Vault deployment itself would need to change.

**Negative / trade-offs:**
- **Vault dev mode is explicitly not production-safe**, and this is a
  known, accepted limitation of this project, not an oversight: dev mode
  auto-unseals, stores everything in memory (all secrets are lost on
  restart), and uses a single static root token instead of a scoped auth
  method. A real deployment would need Integrated Storage (Raft) or an
  external backend, auto-unseal via a cloud KMS, and the Kubernetes Auth
  Method (so Platform API authenticates with its own ServiceAccount token
  rather than a shared root token) instead of what's implemented here.
- `VAULT_TOKEN` itself is still a static credential sitting in `.env` —
  this migration reduces the number of secrets in `.env` from several to
  one, but does not eliminate static credentials in local configuration
  entirely.
- Introduces a new runtime dependency: if Vault is unreachable, Platform
  API cannot provision anything, since both GitHub and ArgoCD
  authentication depend on it. Previously, a missing `.env` value would
  fail immediately and obviously at startup (a Pydantic validation error);
  now, a Vault outage fails lazily, on the first request that needs a
  secret Vault can't currently provide.
