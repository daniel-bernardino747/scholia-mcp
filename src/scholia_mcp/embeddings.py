"""Embedding providers behind one small interface."""

from typing import Literal, Protocol

import httpx

from scholia_mcp.config import Settings

InputType = Literal["document", "query"]


class Embedder(Protocol):
    provider: str
    model: str
    dim: int

    def embed(self, texts: list[str], input_type: InputType) -> list[list[float]]: ...


# Default output dimension of each supported Voyage model.
VOYAGE_DIMS = {
    "voyage-3.5-lite": 1024,
    "voyage-3.5": 1024,
    "voyage-3-large": 1024,
    "voyage-3-lite": 512,
    "voyage-3": 1024,
    "voyage-multilingual-2": 1024,
}


class VoyageEmbedder:
    provider = "voyage"

    def __init__(self, api_key: str, model: str, client: httpx.Client | None = None):
        if model not in VOYAGE_DIMS:
            raise ValueError(f"Unknown Voyage model {model!r}; known: {sorted(VOYAGE_DIMS)}")
        self.model = model
        self.dim = VOYAGE_DIMS[model]
        self._client = client or httpx.Client(base_url="https://api.voyageai.com/v1", timeout=30)
        self._api_key = api_key

    def embed(self, texts: list[str], input_type: InputType) -> list[list[float]]:
        response = self._client.post(
            "/embeddings",
            headers={"Authorization": f"Bearer {self._api_key}"},
            json={"input": texts, "model": self.model, "input_type": input_type},
        )
        response.raise_for_status()
        data = sorted(response.json()["data"], key=lambda item: item["index"])
        return [item["embedding"] for item in data]


# Output dimension requested from each supported OpenAI model. pgvector's HNSW
# index takes at most 2000 dimensions, so text-embedding-3-large (3072 by
# default) is shortened, which OpenAI supports natively for the -3 models.
OPENAI_DIMS = {
    "text-embedding-3-small": 1536,
    "text-embedding-3-large": 1536,
}


class OpenAIEmbedder:
    provider = "openai"

    def __init__(self, api_key: str, model: str, client: httpx.Client | None = None):
        if model not in OPENAI_DIMS:
            raise ValueError(f"Unknown OpenAI model {model!r}; known: {sorted(OPENAI_DIMS)}")
        self.model = model
        self.dim = OPENAI_DIMS[model]
        self._client = client or httpx.Client(base_url="https://api.openai.com/v1", timeout=30)
        self._api_key = api_key

    def embed(self, texts: list[str], input_type: InputType) -> list[list[float]]:
        # OpenAI embeds documents and queries the same way; input_type is unused.
        response = self._client.post(
            "/embeddings",
            headers={"Authorization": f"Bearer {self._api_key}"},
            json={"model": self.model, "input": texts, "dimensions": self.dim},
        )
        response.raise_for_status()
        data = sorted(response.json()["data"], key=lambda item: item["index"])
        return [item["embedding"] for item in data]


class OllamaEmbedder:
    """A local Ollama server. Any embedding model works: the dimension is probed."""

    provider = "ollama"

    def __init__(
        self,
        model: str,
        base_url: str = "http://localhost:11434",
        client: httpx.Client | None = None,
    ):
        self.model = model
        # Local models can be slow to load on first use.
        self._client = client or httpx.Client(base_url=base_url, timeout=120)
        [probe] = self.embed(["dimension probe"], "query")
        self.dim = len(probe)

    def embed(self, texts: list[str], input_type: InputType) -> list[list[float]]:
        # Ollama has no query/document distinction; input_type is unused.
        response = self._client.post("/api/embed", json={"model": self.model, "input": texts})
        response.raise_for_status()
        return response.json()["embeddings"]


def build_embedder(settings: Settings) -> Embedder:
    match settings.embedding_provider:
        case "voyage":
            assert settings.voyage_api_key  # guaranteed by Settings
            return VoyageEmbedder(settings.voyage_api_key, settings.embedding_model)
        case "openai":
            assert settings.openai_api_key  # guaranteed by Settings
            return OpenAIEmbedder(settings.openai_api_key, settings.embedding_model)
        case "ollama":
            return OllamaEmbedder(settings.embedding_model, settings.ollama_url)
