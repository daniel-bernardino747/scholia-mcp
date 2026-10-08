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
        self._client = client or httpx.Client(
            base_url="https://api.voyageai.com/v1",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=30,
        )

    def embed(self, texts: list[str], input_type: InputType) -> list[list[float]]:
        response = self._client.post(
            "/embeddings",
            json={"input": texts, "model": self.model, "input_type": input_type},
        )
        response.raise_for_status()
        data = sorted(response.json()["data"], key=lambda item: item["index"])
        return [item["embedding"] for item in data]


def build_embedder(settings: Settings) -> Embedder:
    match settings.embedding_provider:
        case "voyage":
            assert settings.voyage_api_key  # guaranteed by Settings
            return VoyageEmbedder(settings.voyage_api_key, settings.embedding_model)
