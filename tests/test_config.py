import pytest
from pydantic import ValidationError

from scholia_mcp.config import Settings

BASE = {
    "DATABASE_URL": "postgresql://u:p@localhost/db",
    "VOYAGE_API_KEY": "vk",
}


def make(monkeypatch, **env):
    for key in (
        "AUTH_MODE",
        "BEARER_TOKEN",
        "EMBEDDING_PROVIDER",
        "VOYAGE_API_KEY",
        "ALLOWED_GITHUB_USERS",
        "FTS_LANGUAGE",
    ):
        monkeypatch.delenv(key, raising=False)
    for key, value in {**BASE, **env}.items():
        monkeypatch.setenv(key, value)
    return Settings(_env_file=None)  # pyright: ignore[reportCallIssue]


def test_bearer_mode_with_token_loads(monkeypatch):
    settings = make(monkeypatch, AUTH_MODE="bearer", BEARER_TOKEN="s3cret")
    assert settings.auth_mode == "bearer"
    assert settings.bearer_token == "s3cret"
    assert settings.fts_language == "english"
    assert settings.embedding_model == "voyage-3.5-lite"


def test_bearer_mode_without_token_refuses_to_load(monkeypatch):
    with pytest.raises(ValidationError, match="BEARER_TOKEN"):
        make(monkeypatch, AUTH_MODE="bearer")


def test_voyage_provider_without_api_key_refuses_to_load(monkeypatch):
    with pytest.raises(ValidationError, match="VOYAGE_API_KEY"):
        make(monkeypatch, BEARER_TOKEN="s3cret", VOYAGE_API_KEY="")


def test_unsupported_auth_mode_refuses_to_load(monkeypatch):
    with pytest.raises(ValidationError, match="auth_mode"):
        make(monkeypatch, AUTH_MODE="none", BEARER_TOKEN="s3cret")


def test_unknown_embedding_provider_refuses_to_load(monkeypatch):
    with pytest.raises(ValidationError, match="embedding_provider"):
        make(monkeypatch, BEARER_TOKEN="s3cret", EMBEDDING_PROVIDER="magic")
