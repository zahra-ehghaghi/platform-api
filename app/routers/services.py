from fastapi import APIRouter, HTTPException
from app.models.service import ServiceCreateRequest, ServiceCreateResponse
from app.clients.github_client import github_client
from app.clients.argocd_client import argocd_client
from app.clients.k8s_client import k8s_client
from app.core.config import settings

router = APIRouter()


@router.post("", response_model=ServiceCreateResponse)
def create_service(request: ServiceCreateRequest):
    try:
        clone_url = github_client.create_repository(
            name=request.name,
            description=f"Service: {request.name} ({request.language.value})"
        )
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))

    github_client.push_template_files(
        repo_name=request.name,
        template_dir=f"app/templates/{request.language.value}",
        replacements={
            "${{values.app_name}}": request.name,
            "${{values.app_env}}": request.environment.value,
        }
    )

    k8s_client.create_namespace(
        namespace=request.environment.value,
        labels={
            "managed-by": "platform-api",
            "environment": request.environment.value,
        },
    )
    k8s_client.ensure_resource_quota(namespace=request.environment.value)
    k8s_client.ensure_limit_range(namespace=request.environment.value)
    k8s_client.ensure_network_policy(namespace=request.environment.value)
    k8s_client.ensure_service_account(namespace=request.environment.value)
    k8s_client.ensure_role(namespace=request.environment.value)
    k8s_client.ensure_role_binding(namespace=request.environment.value)    

    repo_https_url = f"https://github.com/{settings.github_org}/{request.name}.git"

    argocd_client.ensure_repo(repo_https_url)
    argocd_client.ensure_app(
        app_name=request.name,
        repo_url=repo_https_url,
        path=f"charts/{request.name}",
        namespace=request.environment.value,
        values_file=f"values-{request.environment.value}.yaml",
    )

    return ServiceCreateResponse(
        name=request.name,
        repo_url=clone_url,
        status="deployed"
    )
