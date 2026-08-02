import httpx
from app.core.config import settings
from app.clients.vault_client import vault_client

TIMEOUT = httpx.Timeout(30.0, connect=10.0)


class ArgocdClient:
    def __init__(self):
        self._base_url = f"https://{settings.argocd_server}/api/v1"
        self._verify_ssl = settings.argocd_verify_ssl
        self._token = None

    def _login(self) -> str:
        if self._token:
            return self._token

        password = vault_client.get_secret("platform-api", "argocd_password")
        response = httpx.post(
            f"{self._base_url}/session",
            json={
                "username": settings.argocd_username,
                "password": password,
            },
            verify=self._verify_ssl,
            timeout=TIMEOUT,
        )
        response.raise_for_status()
        self._token = response.json()["token"]
        return self._token

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self._login()}"}

    def ensure_repo(self, repo_url: str):
        response = httpx.get(
            f"{self._base_url}/repositories",
            headers=self._headers(),
            verify=self._verify_ssl,
            timeout=TIMEOUT,
        )
        response.raise_for_status()
        existing_repos = [r["repo"] for r in (response.json().get("items") or [])]

        if repo_url in existing_repos:
            return

        response = httpx.post(
            f"{self._base_url}/repositories",
            headers=self._headers(),
            json={"repo": repo_url},
            verify=self._verify_ssl,
            timeout=TIMEOUT,
        )
        response.raise_for_status()

    def ensure_app(self, app_name: str, repo_url: str, path: str, namespace: str, values_file: str):
        response = httpx.get(
            f"{self._base_url}/applications/{app_name}",
            headers=self._headers(),
            verify=self._verify_ssl,
            timeout=TIMEOUT,
        )

        if response.status_code == 200:
            return

        payload = {
            "metadata": {"name": app_name},
            "spec": {
                "project": "default",
                "source": {
                    "repoURL": repo_url,
                    "path": path,
                    "targetRevision": "main",
                    "helm": {"valueFiles": [values_file]},
                },
                "destination": {
                    "server": "https://kubernetes.default.svc",
                    "namespace": namespace,
                },
                "syncPolicy": {
                    "automated": {"prune": True, "selfHeal": True},
                    "syncOptions": ["CreateNamespace=true"],
                },
            },
        }

        response = httpx.post(
            f"{self._base_url}/applications",
            headers=self._headers(),
            json=payload,
            verify=self._verify_ssl,
            timeout=TIMEOUT,
        )
        response.raise_for_status()

    def sync_app(self, app_name: str):
        response = httpx.post(
            f"{self._base_url}/applications/{app_name}/sync",
            headers=self._headers(),
            json={},
            verify=self._verify_ssl,
            timeout=TIMEOUT,
        )
        response.raise_for_status()


argocd_client = ArgocdClient()
