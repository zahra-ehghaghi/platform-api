from unittest.mock import MagicMock, patch

import pytest
from github import GithubException

from app.clients.github_client import GithubClient


@pytest.fixture
def mock_github():
    """
    Patches the `Github` class used inside github_client.py so that
    instantiating GithubClient() never makes a real network call, and
    returns the mock organization object for assertions.
    """
    with patch("app.clients.github_client.Github") as MockGithub:
        mock_org = MagicMock()
        MockGithub.return_value.get_organization.return_value = mock_org
        yield mock_org


class TestLazyOrganizationLookup:
    def test_constructing_client_does_not_call_get_organization(self):
        with patch("app.clients.github_client.Github") as MockGithub:
            GithubClient()

            MockGithub.return_value.get_organization.assert_not_called()

    def test_org_lookup_happens_once_and_is_cached(self):
        with patch("app.clients.github_client.Github") as MockGithub:
            client = GithubClient()

            # Trigger two operations that both need self._org
            client.get_repo("service-a")
            client.get_repo("service-b")

            # get_organization should only have been called once, even
            # though _org was accessed twice - the second access hits the
            # cached value instead of calling the API again.
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
