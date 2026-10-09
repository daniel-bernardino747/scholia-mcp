"""Runtime configuration, read from the environment.

Fail-closed: a configuration that would leave the server open (or unable to
embed) is rejected at load time, so the server never starts with it.
"""

from typing import Literal, Self

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str

    # "github" (OAuth with an allowlist) arrives with the Railway deploy.
    auth_mode: Literal["bearer"] = "bearer"
    bearer_token: str | None = None

    embedding_provider: Literal["voyage"] = "voyage"
    embedding_model: str = "voyage-3.5-lite"
    voyage_api_key: str | None = None

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
        if self.embedding_provider == "voyage" and not self.voyage_api_key:
            raise ValueError("EMBEDDING_PROVIDER=voyage requires VOYAGE_API_KEY")
        return self
