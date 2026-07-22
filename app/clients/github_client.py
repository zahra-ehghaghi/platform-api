import os
from github import Github, GithubException, InputGitTreeElement
from app.core.config import settings


class GithubClient:
    def __init__(self):
        self._client = Github(settings.github_token)
        self._org = self._client.get_organization(settings.github_org)

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
