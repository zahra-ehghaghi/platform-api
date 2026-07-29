"""
Session-wide test setup: ensures required Settings fields (see
app/core/config.py) have a value before any app.* module is imported,
since Settings() raises a validation error at import time otherwise.

Note: this file no longer needs to patch github.Github or Kubernetes config
loading globally. Both GithubClient and K8sClient now defer their real I/O
(get_organization(), load_kube_config()) to first use via a lazy property,
instead of doing it in __init__ - so importing these modules, or
instantiating their module-level singletons, is safe without network
access or credentials. Individual tests still patch what they need
locally (see test_github_client.py, test_argocd_client.py).
"""

import os

os.environ.setdefault("GITHUB_TOKEN", "test-token")
os.environ.setdefault("GITHUB_ORG", "test-org")
os.environ.setdefault("ARGOCD_SERVER", "argocd.test.local")
os.environ.setdefault("ARGOCD_USERNAME", "admin")
os.environ.setdefault("ARGOCD_PASSWORD", "test-password")
os.environ.setdefault("DOCKERHUB_USERNAME", "test-user")
