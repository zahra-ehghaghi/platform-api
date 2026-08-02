"""
Session-wide test setup: ensures required Settings fields (see
app/core/config.py) have a value before any app.* module is imported,
since Settings() raises a validation error at import time otherwise.

Note: GithubClient and K8sClient use lazy initialization, so importing
these modules is safe without network access. Individual tests still patch
what they need locally - including Vault reads via VaultClient.get_secret,
which is now called by both GithubClient and ArgocdClient (see
test_github_client.py and test_argocd_client.py).
"""

import os

os.environ.setdefault("VAULT_ADDR", "http://vault.test.local")
os.environ.setdefault("VAULT_TOKEN", "test-vault-token")
os.environ.setdefault("GITHUB_ORG", "test-org")
os.environ.setdefault("ARGOCD_SERVER", "argocd.test.local")
os.environ.setdefault("ARGOCD_USERNAME", "admin")
os.environ.setdefault("DOCKERHUB_USERNAME", "test-user")
