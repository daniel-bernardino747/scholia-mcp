"""Runtime configuration, read from the environment.

Fail-closed: a configuration that would leave the server open (or unable to
embed) is rejected at load time, so the server never starts with it.
"""

from typing import Literal, Self

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_MODELS = {
    "voyage": "voyage-3.5-lite",
    "openai": "text-embedding-3-small",
    "ollama": "bge-m3",  # multilingual
}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str

    auth_mode: Literal["bearer", "github"] = "bearer"
    bearer_token: str | None = None

    # GitHub logins allowed in, comma-separated (GitHub logins are case-insensitive).
    allowed_github_users: str = ""
    github_client_id: str | None = None
    github_client_secret: str | None = None
    # Public URL of this server, used for OAuth callbacks (e.g. https://x.up.railway.app).
    base_url: str | None = None

    embedding_provider: Literal["voyage", "openai", "ollama"] = "voyage"
    # Empty means the provider's default (see DEFAULT_MODELS).
    embedding_model: str = ""
    voyage_api_key: str | None = None
    openai_api_key: str | None = None
    ollama_url: str = "http://localhost:11434"

    fts_language: str = "english"

    # Cosine similarity a note needs to be returned without a term match.
    # 0 disables the floor; calibrate against real scores before raising it.
    min_similarity: float = Field(default=0.0, ge=0.0, le=1.0)

    host: str = "0.0.0.0"
    port: int = 8000

    @model_validator(mode="after")
    def _fail_closed(self) -> Self:
        if self.auth_mode == "bearer" and not self.bearer_token:
            raise ValueError("AUTH_MODE=bearer requires BEARER_TOKEN")
        if self.auth_mode == "github":
            required = {
                "ALLOWED_GITHUB_USERS": self.github_allowlist,
                "GITHUB_CLIENT_ID": self.github_client_id,
                "GITHUB_CLIENT_SECRET": self.github_client_secret,
                "BASE_URL": self.base_url,
            }
            missing = [name for name, value in required.items() if not value]
            if missing:
                raise ValueError(f"AUTH_MODE=github requires {', '.join(missing)}")
        if self.embedding_provider == "voyage" and not self.voyage_api_key:
            raise ValueError("EMBEDDING_PROVIDER=voyage requires VOYAGE_API_KEY")
        if self.embedding_provider == "openai" and not self.openai_api_key:
            raise ValueError("EMBEDDING_PROVIDER=openai requires OPENAI_API_KEY")
        if not self.embedding_model:
            self.embedding_model = DEFAULT_MODELS[self.embedding_provider]
        return self

    @property
    def github_allowlist(self) -> set[str]:
        return {login.strip().lower() for login in self.allowed_github_users.split(",")} - {""}
