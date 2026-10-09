import httpx2

from scholia_mcp.auth import AllowlistGitHubVerifier

# GitHub accounts by login. "renamed" is octocat's account after a rename, and
# "squatter" is someone else who registered a login. IDs never change.
GITHUB_IDS = {"OctoCat": 583231, "renamed": 583231, "mallory": 666, "squatter": 777}


def fake_github(request: httpx2.Request) -> httpx2.Response:
    """GitHub's API, where the token `gho_<login>` belongs to that user."""
    login = request.headers.get("Authorization", "").removeprefix("Bearer gho_")
    if login not in GITHUB_IDS:
        return httpx2.Response(401, json={"message": "Bad credentials"})
    if request.url.path == "/user":
        return httpx2.Response(200, json={"id": GITHUB_IDS[login], "login": login})
    return httpx2.Response(200, json=[], headers={"X-OAuth-Scopes": "read:user"})


def make_verifier(*allowed: str) -> AllowlistGitHubVerifier:
    client = httpx2.AsyncClient(transport=httpx2.MockTransport(fake_github))
    return AllowlistGitHubVerifier(allowed=set(allowed), http_client=client)


async def test_allowed_user_is_let_in_whatever_the_case_of_their_login():
    token = await make_verifier("octocat").verify_token("gho_OctoCat")

    assert token is not None
    assert token.claims["login"] == "OctoCat"


async def test_valid_github_user_outside_the_allowlist_is_rejected():
    assert await make_verifier("octocat").verify_token("gho_mallory") is None


async def test_invalid_github_token_is_rejected():
    assert await make_verifier("octocat").verify_token("not-a-github-token") is None


async def test_user_allowlisted_by_id_is_let_in_after_renaming_their_login():
    assert await make_verifier("583231").verify_token("gho_renamed") is not None


async def test_allowlisting_by_id_rejects_a_different_account_whatever_its_login():
    assert await make_verifier("583231").verify_token("gho_squatter") is None
