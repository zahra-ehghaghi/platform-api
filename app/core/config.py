from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    github_token: str
    github_org: str = "zahra-ehghaghi-org"
    argocd_server: str = "argocd-server.argocd"
    argocd_username: str = "admin"
    argocd_password: str
    dockerhub_username: str
    argocd_verify_ssl: bool = False
    
    class Config:
        env_file = ".env"

settings = Settings()
