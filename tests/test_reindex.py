import pytest
from conftest import FakeEmbedder
from fastmcp import Client

from scholia_mcp.server import create_server
from scholia_mcp.store import open_store, reindex


async def save(client, **fields):
    note = {"tags": [], "sources": [], "origin_agent": "claude-code", **fields}
    return (await client.call_tool("save_note", note)).structured_content


async def search(client, query, **options):
    result = await client.call_tool("search_notes", {"query": query, **options})
    return result.structured_content["results"]


@pytest.fixture
async def saved(database_url, embedder):
    """A database built with the 8-dim fake embedder and English, with history."""
    with open_store(database_url, embedder, "english") as store:
        async with Client(create_server(store)) as client:
            old = await save(client, title="Coffee", body="Espresso helps my focus.")
            new = await save(client, title="Coffee v2", body="Decaf only.", supersedes=old["id"])
            car = await save(client, title="Buying a car", body="Electric cars cost less.")
    return {"old": old, "new": new, "car": car}


async def test_after_reindex_the_server_boots_with_the_new_settings(database_url, saved):
    reindex(database_url, FakeEmbedder(dim=16), "portuguese")

    with open_store(database_url, FakeEmbedder(dim=16), "portuguese") as store:
        assert store.meta() == {
            "embedding_provider": "fake",
            "embedding_model": "concepts-v1",
            "embedding_dim": 16,
            "fts_language": "portuguese",
        }


async def test_after_reindex_notes_are_found_by_meaning_and_keep_their_history(database_url, saved):
    reindex(database_url, FakeEmbedder(dim=16), "portuguese")

    with open_store(database_url, FakeEmbedder(dim=16), "portuguese") as store:
        async with Client(create_server(store)) as client:
            by_meaning = await search(client, "automobile")
            history = await search(client, "espresso", include_superseded=True)

    assert by_meaning[0]["id"] == saved["car"]["id"]
    assert {r["id"]: r["status"] for r in history if r["title"].startswith("Coffee")} == {
        saved["old"]["id"]: "superseded",
        saved["new"]["id"]: "active",
    }


class FailingEmbedder(FakeEmbedder):
    def embed(self, texts, input_type):
        raise RuntimeError("embedding API down")


async def test_failed_reindex_leaves_the_database_as_it_was(database_url, embedder, saved):
    with pytest.raises(RuntimeError, match="API down"):
        reindex(database_url, FailingEmbedder(dim=16), "portuguese")

    with open_store(database_url, embedder, "english") as store:
        async with Client(create_server(store)) as client:
            assert (await search(client, "automobile"))[0]["id"] == saved["car"]["id"]
