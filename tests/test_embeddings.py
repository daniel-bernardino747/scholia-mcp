import json

import httpx

from scholia_mcp.embeddings import OpenAIEmbedder


def fake_openai(requests: list[dict]):
    """OpenAI's embeddings API; answers out of order, as the API may."""

    def handle(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        requests.append({"auth": request.headers["Authorization"], **body})
        data = [
            {"object": "embedding", "index": i, "embedding": [float(i)] * body["dimensions"]}
            for i in range(len(body["input"]))
        ]
        return httpx.Response(200, json={"object": "list", "data": list(reversed(data))})

    return httpx.Client(base_url="https://api.openai.com/v1", transport=httpx.MockTransport(handle))


def test_openai_embedder_returns_one_vector_per_text_in_input_order():
    requests: list[dict] = []
    embedder = OpenAIEmbedder("sk-test", "text-embedding-3-small", client=fake_openai(requests))

    vectors = embedder.embed(["first", "second"], "document")

    assert [v[0] for v in vectors] == [0.0, 1.0]
    assert embedder.dim == 1536
    assert requests == [
        {
            "auth": "Bearer sk-test",
            "model": "text-embedding-3-small",
            "input": ["first", "second"],
            "dimensions": 1536,
        }
    ]


def test_large_model_is_shortened_to_fit_the_hnsw_index():
    requests: list[dict] = []
    embedder = OpenAIEmbedder("sk-test", "text-embedding-3-large", client=fake_openai(requests))

    [vector] = embedder.embed(["text"], "query")

    assert embedder.dim == len(vector) == requests[0]["dimensions"] == 1536
