from unittest.mock import MagicMock, patch

import pytest
from github import GithubException

from app.clients.github_client import GithubClient


@pytest.fixture
def mock_github():
    """
    Patches both the Vault read (so GithubClient's lazy _client property
    doesn't try to make a real Vault call) and the `Github` class itself,
    so instantiating GithubClient() and using it never makes a real network
    call. Yields the mock organization object for assertions.
    """
    with patch("app.clients.github_client.vault_client.get_secret", return_value="fake-token"), \
         patch("app.clients.github_client.Github") as MockGithub:
        mock_org = MagicMock()
        MockGithub.return_value.get_organization.return_value = mock_org
        yield mock_org


class TestLazyInitialization:
    def test_constructing_client_does_not_call_vault_or_github(self):
        with patch("app.clients.github_client.vault_client.get_secret") as mock_get_secret, \
             patch("app.clients.github_client.Github") as MockGithub:
            GithubClient()

            mock_get_secret.assert_not_called()
            MockGithub.return_value.get_organization.assert_not_called()

    def test_vault_and_org_lookup_happen_once_and_are_cached(self):
        with patch("app.clients.github_client.vault_client.get_secret", return_value="fake-token") as mock_get_secret, \
             patch("app.clients.github_client.Github") as MockGithub:
            client = GithubClient()

            client.get_repo("service-a")
            client.get_repo("service-b")

            # Both the Vault read and the org lookup should only happen
            # once, even though two operations needed them - the second
            # access hits the cached values instead of repeating the calls.
            mock_get_secret.assert_called_once_with("platform-api", "github_token")
            MockGithub.return_value.get_organization.assert_called_once()


class TestCreateRepository:
    def test_creates_repo_and_returns_clone_url(self, mock_github):
        mock_repo = MagicMock()
        mock_repo.clone_url = "https://github.com/test-org/my-service.git"
        mock_github.create_repo.return_value = mock_repo

        client = GithubClient()
        result = client.create_repository(name="my-service", description="test")

        assert result == "https://github.com/test-org/my-service.git"
        mock_github.create_repo.assert_called_once_with(
            name="my-service",
            description="test",
            private=False,
            auto_init=True,
        )

    def test_existing_repo_raises_value_error(self, mock_github):
        error = GithubException(status=422, data={"message": "already exists"}, headers=None)
        mock_github.create_repo.side_effect = error

        client = GithubClient()

        with pytest.raises(ValueError, match="already exists"):
            client.create_repository(name="my-service", description="test")

    def test_unexpected_github_error_is_reraised(self, mock_github):
        error = GithubException(status=500, data={"message": "server error"}, headers=None)
        mock_github.create_repo.side_effect = error

        client = GithubClient()

        with pytest.raises(GithubException):
            client.create_repository(name="my-service", description="test")

