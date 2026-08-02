from unittest.mock import MagicMock, patch

import pytest

from app.clients.argocd_client import ArgocdClient


@pytest.fixture
def client():
    return ArgocdClient()


@pytest.fixture(autouse=True)
def mock_vault_password():
    """
    _login() now reads the ArgoCD password from Vault before calling the
    session endpoint. Applied automatically to every test in this file so
    individual tests don't need to remember to patch it.
    """
    with patch(
        "app.clients.argocd_client.vault_client.get_secret",
        return_value="fake-password",
    ):
        yield


def _mock_response(status_code=200, json_data=None):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data or {}
    resp.raise_for_status = MagicMock()
    return resp


class TestLogin:
    @patch("app.clients.argocd_client.httpx.post")
    def test_login_caches_token_across_calls(self, mock_post, client):
        mock_post.return_value = _mock_response(json_data={"token": "fake-token"})

        token1 = client._login()
        token2 = client._login()

        assert token1 == "fake-token"
        assert token2 == "fake-token"
        # Only one real HTTP call should have been made - the second call
        # should hit the cached self._token instead of calling the session
        # endpoint again.
        mock_post.assert_called_once()


class TestEnsureRepo:
    @patch("app.clients.argocd_client.httpx.post")
    @patch("app.clients.argocd_client.httpx.get")
    def test_registers_new_repo_when_not_present(self, mock_get, mock_post, client):
        mock_get.return_value = _mock_response(json_data={"items": []})
        mock_post.side_effect = [
            _mock_response(json_data={"token": "fake-token"}),  # login
            _mock_response(),  # repo create
        ]

        client.ensure_repo("https://github.com/test-org/my-service.git")

        # The second POST call should be the repo-add request
        assert mock_post.call_count == 2

    @patch("app.clients.argocd_client.httpx.post")
    @patch("app.clients.argocd_client.httpx.get")
    def test_skips_creation_when_repo_already_registered(self, mock_get, mock_post, client):
        mock_get.return_value = _mock_response(
            json_data={"items": [{"repo": "https://github.com/test-org/my-service.git"}]}
        )
        mock_post.return_value = _mock_response(json_data={"token": "fake-token"})  # login only

        client.ensure_repo("https://github.com/test-org/my-service.git")

        # Only the login call should have happened - no repo-add POST
        mock_post.assert_called_once()

    @patch("app.clients.argocd_client.httpx.post")
    @patch("app.clients.argocd_client.httpx.get")
    def test_handles_null_items_from_argocd(self, mock_get, mock_post, client):
        """
        Regression test: ArgoCD returns {"items": null} (not an absent key)
        when no repositories are registered yet. `.get("items", [])` alone
        does not catch this - only `.get("items") or []` does.
        """
        mock_get.return_value = _mock_response(json_data={"items": None})
        mock_post.side_effect = [
            _mock_response(json_data={"token": "fake-token"}),
            _mock_response(),
        ]

        # Should not raise TypeError: 'NoneType' object is not iterable
        client.ensure_repo("https://github.com/test-org/my-service.git")

        assert mock_post.call_count == 2

