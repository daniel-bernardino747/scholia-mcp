"""Who may call the server: a shared bearer token, or allowlisted GitHub users."""

import hmac

import httpx2
from cryptography.fernet import Fernet
from fastmcp.server.auth import AccessToken, AuthProvider, TokenVerifier
from fastmcp.server.auth.jwt_issuer import derive_jwt_key
from fastmcp.server.auth.oauth_proxy import OAuthProxy
from fastmcp.server.auth.providers.github import GitHubTokenVerifier
from key_value.aio.stores.postgresql import PostgreSQLStore
from key_value.aio.wrappers.encryption import FernetEncryptionWrapper

from scholia_mcp.config import Settings

# FastMCP's salt for deriving the OAuth storage key. Changing it makes every
# stored registration and token unreadable (all clients must log in again).
_STORAGE_KEY_SALT = "fastmcp-storage-encryption-key"


class StaticBearerVerifier(TokenVerifier):
    """Accepts exactly one shared token, compared in constant time."""

    def __init__(self, token: str):
        super().__init__()
        self._token = token.encode()

    async def verify_token(self, token: str) -> AccessToken | None:
        if not hmac.compare_digest(token.encode(), self._token):
            return None
        return AccessToken(token=token, client_id="bearer", scopes=[])


class AllowlistGitHubVerifier(GitHubTokenVerifier):
    """A GitHub token verifier that only lets in the given accounts.

    Entries are logins (case-insensitive) or numeric account IDs. IDs are
    safer: a login can be renamed and then registered by someone else.
    Runs on every request, so removing an entry revokes access immediately.
    """

    def __init__(self, allowed: set[str], http_client: httpx2.AsyncClient | None = None):
        # read:user is enough to identify the user; "user" would also grant writes.
        super().__init__(required_scopes=["read:user"], http_client=http_client)
        self._allowed = {entry.lower() for entry in allowed}

    async def verify_token(self, token: str) -> AccessToken | None:
        verified = await super().verify_token(token)
        if verified is None:
            return None
        login = str(verified.claims.get("login") or "").lower()
        account_id = str(verified.claims.get("sub") or "")
        return verified if {login, account_id} & self._allowed else None


def build_auth(settings: Settings) -> AuthProvider:
    match settings.auth_mode:
        case "bearer":
            assert settings.bearer_token  # guaranteed by Settings
            return StaticBearerVerifier(settings.bearer_token)
        case "github":
            return _github_auth(settings)


def _github_auth(settings: Settings) -> AuthProvider:
    # All guaranteed by Settings in github mode.
    assert settings.github_client_id and settings.github_client_secret and settings.base_url
    # OAuth state (client registrations, upstream tokens) lives in Postgres, so
    # it survives redeploys; encrypted with a key derived from the client secret,
    # as FastMCP does for its default file store.
    storage_key = derive_jwt_key(
        high_entropy_material=settings.github_client_secret,
        salt=_STORAGE_KEY_SALT,
    )
    storage = FernetEncryptionWrapper(
        key_value=PostgreSQLStore(url=settings.database_url, table_name="oauth_state"),
        fernet=Fernet(key=storage_key),
        raise_on_decryption_error=False,
    )
    return OAuthProxy(
        upstream_authorization_endpoint="https://github.com/login/oauth/authorize",
        upstream_token_endpoint="https://github.com/login/oauth/access_token",
        upstream_client_id=settings.github_client_id,
        upstream_client_secret=settings.github_client_secret,
        token_verifier=AllowlistGitHubVerifier(settings.github_allowlist),
        base_url=settings.base_url,
        client_storage=storage,
    )
