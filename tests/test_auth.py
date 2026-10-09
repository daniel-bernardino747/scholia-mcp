import httpx2
import pytest

from scholia_mcp.auth import AllowlistGitHubVerifier


def fake_github(request: httpx2.Request) -> httpx2.Response:
    """GitHub's API, where the token `gho_<login>` belongs to that user."""
    token = request.headers.get("Authorization", "").removeprefix("Bearer ")
    if not token.startswith("gho_"):
        return httpx2.Response(401, json={"message": "Bad credentials"})
    if request.url.path == "/user":
        return httpx2.Response(200, json={"id": 1, "login": token.removeprefix("gho_")})
    return httpx2.Response(200, json=[], headers={"X-OAuth-Scopes": "user"})


@pytest.fixture
def verifier():
    client = httpx2.AsyncClient(transport=httpx2.MockTransport(fake_github))
    return AllowlistGitHubVerifier(allowed={"octocat"}, http_client=client)


async def test_allowed_user_is_let_in_whatever_the_case_of_their_login(verifier):
    token = await verifier.verify_token("gho_OctoCat")

    assert token is not None
    assert token.claims["login"] == "OctoCat"


async def test_valid_github_user_outside_the_allowlist_is_rejected(verifier):
    assert await verifier.verify_token("gho_mallory") is None


async def test_invalid_github_token_is_rejected(verifier):
    assert await verifier.verify_token("not-a-github-token") is None
