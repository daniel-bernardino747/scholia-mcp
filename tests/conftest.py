import math
import os
import re
import unicodedata

import psycopg
import pytest

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql://scholia:scholia@localhost:54330/scholia_test"
)

# Each axis is one "concept"; words on the same axis are synonyms to the fake.
CONCEPTS = [
    {"car", "cars", "automobile", "automobiles", "vehicle", "carro"},
    {"database", "databases", "postgres", "postgresql", "banco"},
    {"search", "retrieval", "lookup", "busca"},
    {"coffee", "espresso", "cafe"},
    {"sleep", "insomnia", "rest", "sono"},
    {"price", "cost", "pricing", "preco"},
    {"opinion", "position", "view"},
]


class FakeEmbedder:
    """Deterministic embedder: a bag of concepts, plus one axis for unknown words."""

    provider = "fake"
    model = "concepts-v1"

    def __init__(self, dim: int = len(CONCEPTS) + 1):
        self.dim = dim

    def embed(self, texts, input_type):
        return [self._vector(text) for text in texts]

    def _vector(self, text):
        plain = unicodedata.normalize("NFKD", text.lower()).encode("ascii", "ignore").decode()
        vector = [0.0] * self.dim
        for word in re.findall(r"[a-z0-9]+", plain):
            axis = next((i for i, c in enumerate(CONCEPTS) if word in c), len(CONCEPTS))
            vector[axis % self.dim] += 1.0
        norm = math.sqrt(sum(x * x for x in vector)) or 1.0
        return [x / norm for x in vector]


@pytest.fixture
def database_url():
    """A test database with an empty public schema."""
    with psycopg.connect(TEST_DATABASE_URL, autocommit=True) as conn:
        conn.execute("DROP SCHEMA public CASCADE")
        conn.execute("CREATE SCHEMA public")
    return TEST_DATABASE_URL


@pytest.fixture
def embedder():
    return FakeEmbedder()
