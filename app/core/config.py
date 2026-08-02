from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    vault_addr: str = "http://vault.test.com"
    vault_token: str

    github_org: str = "zahra-ehghaghi-org"
    argocd_server: str = "argocd.test.com"
    argocd_username: str = "admin"
    argocd_verify_ssl: bool = False
    dockerhub_username: str = ""

    model_config = SettingsConfigDict(env_file=".env")


settings = Settings()
