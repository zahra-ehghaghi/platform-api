from pydantic import BaseModel, Field
from enum import Enum

class Language(str, Enum):
    python = "python"
    node = "node"
    go = "go"

class Environment(str, Enum):
    dev = "dev"
    prod = "prod"

class ServiceCreateRequest(BaseModel):
    name: str = Field(..., pattern=r'^[a-z][a-z0-9-]*$', min_length=3, max_length=30)
    language: Language
    environment: Environment
    owner: str = "development"

class ServiceCreateResponse(BaseModel):
    name: str
    repo_url: str
    status: str
