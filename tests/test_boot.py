import pytest
from conftest import FakeEmbedder

from scholia_mcp.store import SchemaMismatch, open_store


def test_first_boot_records_embedding_and_language_settings(database_url, embedder):
    with open_store(database_url, embedder, "english") as store:
        assert store.meta() == {
            "embedding_provider": "fake",
            "embedding_model": "concepts-v1",
            "embedding_dim": embedder.dim,
            "fts_language": "english",
        }


def test_reboot_with_same_settings_starts(database_url, embedder):
    with open_store(database_url, embedder, "english"):
        pass
    with open_store(database_url, embedder, "english") as store:
        assert store.meta()["embedding_dim"] == embedder.dim


def test_reboot_with_different_dimension_refuses_and_points_to_reindex(database_url, embedder):
    with open_store(database_url, embedder, "english"):
        pass
    with pytest.raises(SchemaMismatch, match="reindex") as excinfo:
        open_store(database_url, FakeEmbedder(dim=16), "english")
    assert "embedding_dim" in str(excinfo.value)


def test_reboot_with_different_language_refuses_and_points_to_reindex(database_url, embedder):
    with open_store(database_url, embedder, "english"):
        pass
    with pytest.raises(SchemaMismatch, match="fts_language.*reindex"):
        open_store(database_url, embedder, "portuguese")


def test_boot_with_unknown_fts_language_refuses(database_url, embedder):
    with pytest.raises(Exception, match="klingon"):
        open_store(database_url, embedder, "klingon")
