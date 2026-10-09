import json

import httpx
import pytest
from conftest import FakeEmbedder
from fastmcp import Client

from scholia_mcp.embeddings import OllamaEmbedder, OpenAIEmbedder, VoyageEmbedder
from scholia_mcp.server import create_server
from scholia_mcp.store import open_store, reindex

CONCEPTS = FakeEmbedder()


def meaningful(text: str, dim: int) -> list[float]:
    """A vector that carries meaning (the fake's concepts), padded to `dim`."""
    vector = CONCEPTS.embed([text], "document")[0]
    return vector + [0.0] * (dim - len(vector))


def fake_api(log: list[dict], respond):
    """An embeddings API that records each request and answers with `respond`."""

    def handle(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content) if request.content else {}
        log.append({"path": request.url.path, "auth": request.headers.get("Authorization"), **body})
        return httpx.Response(200, json=respond(body))

    return httpx.Client(base_url="https://api.test", transport=httpx.MockTransport(handle))


def voyage_api(log, dim=1024):
    return fake_api(
        log,
        lambda body: {
            "data": [
                {"index": i, "embedding": meaningful(text, dim)}
                for i, text in reversed(list(enumerate(body["input"])))
            ]
        },
    )


def openai_api(log):
    return fake_api(
        log,
        lambda body: {
            "data": [
                {"index": i, "embedding": meaningful(text, body["dimensions"])}
                for i, text in reversed(list(enumerate(body["input"])))
            ]
        },
    )


def ollama_api(log, dim=1024):
    return fake_api(
        log, lambda body: {"embeddings": [meaningful(text, dim) for text in body["input"]]}
    )


def test_voyage_embedder_sends_input_type_and_returns_vectors_in_input_order():
    log: list[dict] = []
    embedder = VoyageEmbedder("pa-test", "voyage-3.5-lite", client=voyage_api(log))

    vectors = embedder.embed(["espresso", "car"], "query")

    assert [v[: CONCEPTS.dim] for v in vectors] == CONCEPTS.embed(["espresso", "car"], "query")
    assert log == [
        {
            "path": "/embeddings",
            "auth": "Bearer pa-test",
            "input": ["espresso", "car"],
            "model": "voyage-3.5-lite",
            "input_type": "query",
        }
    ]


def test_openai_embedder_returns_one_vector_per_text_in_input_order():
    log: list[dict] = []
    embedder = OpenAIEmbedder("sk-test", "text-embedding-3-small", client=openai_api(log))

    vectors = embedder.embed(["espresso", "car"], "document")

    assert [v[: CONCEPTS.dim] for v in vectors] == CONCEPTS.embed(["espresso", "car"], "query")
    assert embedder.dim == 1536
    assert log == [
        {
            "path": "/embeddings",
            "auth": "Bearer sk-test",
            "model": "text-embedding-3-small",
            "input": ["espresso", "car"],
            "dimensions": 1536,
        }
    ]


def test_openai_large_model_is_shortened_to_fit_the_hnsw_index():
    log: list[dict] = []
    embedder = OpenAIEmbedder("sk-test", "text-embedding-3-large", client=openai_api(log))

    [vector] = embedder.embed(["text"], "query")

    assert embedder.dim == len(vector) == log[0]["dimensions"] == 1536


def test_ollama_embedder_learns_its_dimension_from_the_model():
    log: list[dict] = []
    embedder = OllamaEmbedder("bge-m3", client=ollama_api(log, dim=768))

    vectors = embedder.embed(["espresso", "car"], "document")

    assert embedder.dim == 768
    assert [len(v) for v in vectors] == [768, 768]
    assert log[-1] == {
        "path": "/api/embed",
        "auth": None,
        "model": "bge-m3",
        "input": ["espresso", "car"],
    }


async def test_switching_from_voyage_to_openai_with_reindex_keeps_search_working(
    database_url,
):
    voyage = VoyageEmbedder("pa-test", "voyage-3.5-lite", client=voyage_api([]))
    with open_store(database_url, voyage, "english") as store:
        async with Client(create_server(store)) as client:
            await client.call_tool(
                "save_note",
                {
                    "title": "Buying a car",
                    "body": "Electric cars cost less to run.",
                    "tags": [],
                    "sources": [],
                    "origin_agent": "test",
                },
            )

    openai = OpenAIEmbedder("sk-test", "text-embedding-3-small", client=openai_api([]))
    reindex(database_url, openai, "english")

    with open_store(database_url, openai, "english") as store:
        async with Client(create_server(store)) as client:
            result = await client.call_tool("search_notes", {"query": "automobile"})
    assert result.structured_content is not None
    assert [r["title"] for r in result.structured_content["results"]] == ["Buying a car"]


def test_unknown_models_are_rejected_before_any_request():
    with pytest.raises(ValueError, match="Unknown OpenAI model"):
        OpenAIEmbedder("sk", "text-embedding-ada-002", client=openai_api([]))
