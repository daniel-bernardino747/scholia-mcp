"""Postgres-backed note store: schema migrations, boot check, save and search."""

import unicodedata
from datetime import datetime
from importlib import resources
from typing import Any, Literal, Self
from uuid import UUID

import psycopg
from psycopg import sql
from psycopg.rows import DictRow, dict_row
from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool
from pydantic import BaseModel

from scholia_mcp.embeddings import Embedder

# Arbitrary key for pg_advisory_lock, so concurrent boots migrate one at a time.
_MIGRATION_LOCK = 0x5C401A


Status = Literal["active", "superseded", "archived"]


class Note(BaseModel):
    id: UUID
    title: str
    body: str
    tags: list[str]
    sources: list[str]
    origin_agent: str
    created_at: datetime
    supersedes: UUID | None
    status: Status


class SearchHit(BaseModel):
    id: UUID
    title: str
    excerpt: str
    tags: list[str]
    created_at: datetime
    status: Status


class NoteNotFound(LookupError):
    pass


class SchemaMismatch(RuntimeError):
    """The database was built with different embedding/FTS settings than configured."""


def open_store(database_url: str, embedder: Embedder, fts_language: str) -> "NoteStore":
    """Migrate the schema, check it matches the configuration, and open a store.

    On an empty database the configured embedder and FTS language are recorded
    in `meta`. On later boots they must match, or SchemaMismatch is raised.
    """
    expected = {
        "embedding_provider": embedder.provider,
        "embedding_model": embedder.model,
        "embedding_dim": embedder.dim,
        "fts_language": fts_language,
    }
    with psycopg.Connection[DictRow].connect(database_url, row_factory=dict_row) as conn:
        conn.execute("SELECT pg_advisory_lock(%s)", (_MIGRATION_LOCK,))
        try:
            _migrate(conn)
            _check_or_init_meta(conn, expected)
        finally:
            conn.execute("SELECT pg_advisory_unlock(%s)", (_MIGRATION_LOCK,))
    return NoteStore(database_url, embedder, fts_language)


def _migrate(conn: psycopg.Connection[DictRow]) -> None:
    conn.execute("CREATE TABLE IF NOT EXISTS schema_migrations (version text PRIMARY KEY)")
    conn.commit()
    applied = {row["version"] for row in conn.execute("SELECT version FROM schema_migrations")}
    scripts = sorted(
        (f for f in resources.files("scholia_mcp.migrations").iterdir() if f.name.endswith(".sql")),
        key=lambda f: f.name,
    )
    for script in scripts:
        version = script.name.removesuffix(".sql")
        if version in applied:
            continue
        with conn.transaction():
            conn.execute(script.read_text(encoding="utf-8").encode())
            conn.execute("INSERT INTO schema_migrations (version) VALUES (%s)", (version,))


def _check_or_init_meta(conn: psycopg.Connection[DictRow], expected: dict[str, Any]) -> None:
    with conn.transaction():
        # Fails early on a language Postgres has no text search config for.
        conn.execute("SELECT %s::regconfig", (expected["fts_language"],))
        current = conn.execute(
            "SELECT embedding_provider, embedding_model, embedding_dim, fts_language FROM meta"
        ).fetchone()
        if current is None:
            dim = int(expected["embedding_dim"])
            conn.execute(
                sql.SQL("ALTER TABLE notes ADD COLUMN embedding vector({}) NOT NULL").format(
                    sql.Literal(dim)
                )
            )
            conn.execute(
                "CREATE INDEX notes_embedding_idx ON notes USING hnsw (embedding vector_cosine_ops)"
            )
            conn.execute(
                "INSERT INTO meta (embedding_provider, embedding_model, embedding_dim,"
                " fts_language) VALUES (%(embedding_provider)s, %(embedding_model)s,"
                " %(embedding_dim)s, %(fts_language)s)",
                expected,
            )
            return
    diffs = [
        f"{key}: database={current[key]!r}, configured={expected[key]!r}"
        for key in expected
        if current[key] != expected[key]
    ]
    if diffs:
        raise SchemaMismatch(
            "Database was indexed with different settings ("
            + "; ".join(diffs)
            + "). Run `scholia-mcp reindex` to rebuild it with the configured ones."
        )


class NoteStore:
    def __init__(self, database_url: str, embedder: Embedder, fts_language: str):
        self._embedder = embedder
        self._fts_language = fts_language
        self._pool = ConnectionPool(
            database_url, kwargs={"row_factory": dict_row}, min_size=1, max_size=5, open=True
        )

    def close(self) -> None:
        self._pool.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def meta(self) -> dict[str, Any]:
        with self._pool.connection() as conn:
            row = conn.execute(
                "SELECT embedding_provider, embedding_model, embedding_dim, fts_language FROM meta"
            ).fetchone()
        assert row is not None
        return row

    def save(
        self,
        title: str,
        body: str,
        tags: list[str],
        sources: list[str],
        origin_agent: str,
        supersedes: UUID | None = None,
    ) -> Note:
        """Insert a note. With `supersedes`, that active note becomes superseded."""
        [embedding] = self._embedder.embed([f"{title}\n\n{body}"], "document")
        with self._pool.connection() as conn, conn.transaction():
            if supersedes is not None:
                replaced = conn.execute(
                    "UPDATE notes SET status = 'superseded'"
                    " WHERE id = %s AND status = 'active' RETURNING id",
                    (supersedes,),
                ).fetchone()
                if replaced is None:
                    raise NoteNotFound(f"No active note with id {supersedes} to supersede")
            row = conn.execute(
                "INSERT INTO notes"
                " (title, body, tags, sources, origin_agent, supersedes, embedding, tsv)"
                " VALUES (%(title)s, %(body)s, %(tags)s, %(sources)s, %(origin_agent)s,"
                " %(supersedes)s, %(embedding)s::vector,"
                " to_tsvector(%(lang)s::regconfig, unaccent(%(title)s || ' ' || %(body)s)))"
                f" RETURNING {_NOTE_COLUMNS}",
                {
                    "title": title,
                    "body": body,
                    "tags": normalize_tags(tags),
                    "sources": Jsonb(sources),
                    "origin_agent": origin_agent,
                    "supersedes": supersedes,
                    "embedding": _vector_literal(embedding),
                    "lang": self._fts_language,
                },
            ).fetchone()
        return Note.model_validate(row)

    def search(
        self,
        query: str,
        tags: list[str] | None = None,
        include_superseded: bool = False,
        limit: int = 8,
    ) -> list[SearchHit]:
        """Hybrid search: vector and full-text rankings fused with RRF.

        Archived notes never appear; superseded ones only on request. With
        `tags`, only notes carrying at least one of them are returned.
        """
        statuses = ["active", "superseded"] if include_superseded else ["active"]
        [embedding] = self._embedder.embed([query], "query")
        with self._pool.connection() as conn:
            rows = conn.execute(
                _SEARCH_SQL,
                {
                    "query": query,
                    "statuses": statuses,
                    "tags": normalize_tags(tags or []),
                    "embedding": _vector_literal(embedding),
                    "lang": self._fts_language,
                    "candidates": max(limit * 5, 40),
                    "rrf_k": _RRF_K,
                    "limit": limit,
                    "excerpt": _EXCERPT_CHARS,
                },
            ).fetchall()
        return [SearchHit.model_validate(row) for row in rows]


_NOTE_COLUMNS = "id, title, body, tags, sources, origin_agent, created_at, supersedes, status"
_EXCERPT_CHARS = 280
# Standard reciprocal rank fusion constant: score = sum(1 / (k + rank)).
_RRF_K = 60

_SEARCH_SQL = """
WITH vector_ranked AS (
    SELECT id, row_number() OVER (ORDER BY embedding <=> %(embedding)s::vector) AS rank
    FROM notes
    WHERE status = ANY(%(statuses)s)
      AND (cardinality(%(tags)s::text[]) = 0 OR tags && %(tags)s::text[])
    ORDER BY embedding <=> %(embedding)s::vector
    LIMIT %(candidates)s
),
text_ranked AS (
    SELECT id, row_number() OVER (ORDER BY ts_rank_cd(tsv, q) DESC) AS rank
    FROM notes, websearch_to_tsquery(%(lang)s::regconfig, unaccent(%(query)s)) q
    WHERE tsv @@ q AND status = ANY(%(statuses)s)
      AND (cardinality(%(tags)s::text[]) = 0 OR tags && %(tags)s::text[])
    ORDER BY ts_rank_cd(tsv, q) DESC
    LIMIT %(candidates)s
),
fused AS (
    SELECT id, sum(1.0 / (%(rrf_k)s + rank)) AS score
    FROM (SELECT * FROM vector_ranked UNION ALL SELECT * FROM text_ranked) ranked
    GROUP BY id
)
SELECT n.id, n.title, left(n.body, %(excerpt)s) AS excerpt, n.tags, n.created_at, n.status
FROM fused JOIN notes n USING (id)
ORDER BY fused.score DESC, n.created_at DESC
LIMIT %(limit)s
"""


def normalize_tags(tags: list[str]) -> list[str]:
    """Lowercase, strip accents and surrounding/repeated spaces, drop duplicates."""
    normalized: list[str] = []
    for tag in tags:
        decomposed = unicodedata.normalize("NFKD", tag)
        plain = "".join(c for c in decomposed if not unicodedata.combining(c))
        tag = " ".join(plain.lower().split())
        if tag and tag not in normalized:
            normalized.append(tag)
    return normalized


def _vector_literal(vector: list[float]) -> str:
    return "[" + ",".join(repr(float(x)) for x in vector) + "]"
