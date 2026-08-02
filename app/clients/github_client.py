import os
from github import Auth, Github, GithubException, InputGitTreeElement
from app.core.config import settings
from app.clients.vault_client import vault_client


class GithubClient:
    def __init__(self):
        self._client_cache = None
        self._org_cache = None

    @property
    def _client(self):
        # Lazy: fetching the token from Vault, and constructing the Github
        # client with it, only happens on first real use - not when
        # GithubClient() is constructed. Same reasoning as the _org lazy
        # property below: a module-level singleton is created as soon as
        # this module is imported, so doing I/O (a Vault call, in this
        # case) directly in __init__ would make importing this file require
        # a reachable Vault instance and a valid token.
        if self._client_cache is None:
            token = vault_client.get_secret("platform-api", "github_token")
            self._client_cache = Github(auth=Auth.Token(token))
        return self._client_cache

    @property
    def _org(self):
        if self._org_cache is None:
            self._org_cache = self._client.get_organization(settings.github_org)
        return self._org_cache

    def create_repository(self, name: str, description: str) -> str:
        try:
            repo = self._org.create_repo(
                name=name,
                description=description,
                private=False,
                auto_init=True,
            )
        except GithubException as e:
            if e.status == 422:
                raise ValueError(f"Repository '{name}' already exists") from e
            raise

        return repo.clone_url

    def get_repo(self, name: str):
        return self._org.get_repo(name)

    def push_template_files(self, repo_name: str, template_dir: str, replacements: dict):
        repo = self.get_repo(repo_name)

        default_branch = repo.default_branch
        ref = repo.get_git_ref(f"heads/{default_branch}")
        base_commit = repo.get_git_commit(ref.object.sha)
        base_tree = base_commit.tree

        element_list = []
        for root, _, files in os.walk(template_dir):
            for filename in files:
                local_path = os.path.join(root, filename)
                relative_path = os.path.relpath(local_path, template_dir)

                for placeholder, value in replacements.items():
                    relative_path = relative_path.replace(placeholder, value)

                with open(local_path, "r") as f:
                    content = f.read()

                for placeholder, value in replacements.items():
                    content = content.replace(placeholder, value)

                blob = repo.create_git_blob(content, "utf-8")
                element = InputGitTreeElement(
                    path=relative_path,
                    mode="100644",
                    type="blob",
                    sha=blob.sha,
                )
                element_list.append(element)

        new_tree = repo.create_git_tree(element_list, base_tree)
        new_commit = repo.create_git_commit(
            message="Initial commit from Platform API",
            tree=new_tree,
            parents=[base_commit],
        )
        ref.edit(new_commit.sha)


github_client = GithubClient()
