import hvac
from app.core.config import settings


class VaultClient:
    def __init__(self):
        self._client = hvac.Client(url=settings.vault_addr, token=settings.vault_token)
        self._cache = {}

    def get_secret(self, path: str, key: str) -> str:
        cache_key = f"{path}:{key}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        response = self._client.secrets.kv.v2.read_secret_version(path=path)
        value = response["data"]["data"][key]
        self._cache[cache_key] = value
        return value


vault_client = VaultClient()
