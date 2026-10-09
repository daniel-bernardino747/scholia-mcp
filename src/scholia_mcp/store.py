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
# pgvector's HNSW index rejects `vector` columns with more dimensions.
_HNSW_MAX_DIM = 2000


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


def open_store(
    database_url: str, embedder: Embedder, fts_language: str, min_similarity: float = 0.0
) -> "NoteStore":
    """Migrate the schema, check it matches the configuration, and open a store.

    On an empty database the configured embedder and FTS language are recorded
    in `meta`. On later boots they must match, or SchemaMismatch is raised.
    """
    _check_dimension(embedder)
    expected = _index_settings(embedder, fts_language)
    with psycopg.Connection[DictRow].connect(database_url, row_factory=dict_row) as conn:
        conn.execute("SELECT pg_advisory_lock(%s)", (_MIGRATION_LOCK,))
        try:
            _migrate(conn)
            _check_or_init_meta(conn, expected)
        finally:
            conn.execute("SELECT pg_advisory_unlock(%s)", (_MIGRATION_LOCK,))
    return NoteStore(database_url, embedder, fts_language, min_similarity)


def reindex(database_url: str, embedder: Embedder, fts_language: str, batch_size: int = 64) -> int:
    """Rebuild every note's embedding and full-text vector with new settings.

    All embeddings are computed before the database is touched, then swapped in
    a single transaction: if the embedding API fails, nothing changes. Run it
    with the server stopped, since a running server still embeds with the old
    settings. Returns the number of notes reindexed.
    """
    _check_dimension(embedder)
    expected = _index_settings(embedder, fts_language)
    with psycopg.Connection[DictRow].connect(database_url, row_factory=dict_row) as conn:
        conn.execute("SELECT pg_advisory_lock(%s)", (_MIGRATION_LOCK,))
        try:
            _migrate(conn)
            conn.execute("SELECT %s::regconfig", (fts_language,))
            notes = conn.execute("SELECT id, title, body FROM notes ORDER BY created_at").fetchall()
            conn.commit()  # don't hold a transaction open across slow API calls
            texts = [_embedding_text(note["title"], note["body"]) for note in notes]
            vectors = [
                vector
                for start in range(0, len(texts), batch_size)
                for vector in embedder.embed(texts[start : start + batch_size], "document")
            ]
            with conn.transaction():
                conn.execute("DROP INDEX IF EXISTS notes_embedding_idx")
                conn.execute("ALTER TABLE notes DROP COLUMN IF EXISTS embedding")
                _add_embedding_column(conn, embedder.dim, nullable=True)
                with conn.cursor() as cursor:
                    cursor.executemany(
                        "UPDATE notes SET embedding = %s::vector WHERE id = %s",
                        [
                            (_vector_literal(v), note["id"])
                            for note, v in zip(notes, vectors, strict=True)
                        ],
                    )
                # Fails (and rolls everything back) if a note arrived meanwhile.
                conn.execute("ALTER TABLE notes ALTER COLUMN embedding SET NOT NULL")
                _create_embedding_index(conn)
                conn.execute(
                    "UPDATE notes SET tsv ="
                    " to_tsvector(%s::regconfig, unaccent(title || ' ' || body))",
                    (fts_language,),
                )
                conn.execute("DELETE FROM meta")
                _insert_meta(conn, expected)
        finally:
            conn.execute("SELECT pg_advisory_unlock(%s)", (_MIGRATION_LOCK,))
    return len(notes)


def _check_dimension(embedder: Embedder) -> None:
    if embedder.dim > _HNSW_MAX_DIM:
        raise ValueError(
            f"{embedder.provider}/{embedder.model} produces {embedder.dim}-dim vectors;"
            f" pgvector's HNSW index supports at most {_HNSW_MAX_DIM}."
        )


def _embedding_text(title: str, body: str) -> str:
    """What gets embedded for a note; save and reindex must agree on it."""
    return f"{title}\n\n{body}"


def _index_settings(embedder: Embedder, fts_language: str) -> dict[str, Any]:
    """What `meta` records about how `embedding` and `tsv` were computed."""
    return {
        "embedding_provider": embedder.provider,
        "embedding_model": embedder.model,
        "embedding_dim": embedder.dim,
        "fts_language": fts_language,
    }


def _add_embedding_column(
    conn: psycopg.Connection[DictRow], dim: int, nullable: bool = False
) -> None:
    conn.execute(
        sql.SQL("ALTER TABLE notes ADD COLUMN embedding vector({}) {}").format(
            sql.Literal(int(dim)), sql.SQL("" if nullable else "NOT NULL")
        )
    )


def _create_embedding_index(conn: psycopg.Connection[DictRow]) -> None:
    conn.execute(
        "CREATE INDEX notes_embedding_idx ON notes USING hnsw (embedding vector_cosine_ops)"
    )


def _insert_meta(conn: psycopg.Connection[DictRow], settings: dict[str, Any]) -> None:
    conn.execute(
        "INSERT INTO meta (embedding_provider, embedding_model, embedding_dim,"
        " fts_language) VALUES (%(embedding_provider)s, %(embedding_model)s,"
        " %(embedding_dim)s, %(fts_language)s)",
        settings,
    )


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
            _add_embedding_column(conn, expected["embedding_dim"])
            _create_embedding_index(conn)
            _insert_meta(conn, expected)
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
            + "). Restore the previous settings, or stop the server and run"
            " `scholia-mcp reindex` to rebuild the index with the configured ones."
        )


class NoteStore:
    def __init__(
        self,
        database_url: str,
        embedder: Embedder,
        fts_language: str,
        min_similarity: float = 0.0,
    ):
        self._embedder = embedder
        self._fts_language = fts_language
        self._index_settings = _index_settings(embedder, fts_language)
        # Notes less similar than this to the query only appear on a term match.
        self._min_similarity = min_similarity
        self._pool = ConnectionPool(
            database_url, kwargs={"row_factory": dict_row}, min_size=1, max_size=5, open=True
        )

    def close(self) -> None:
        self._pool.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def _ensure_current(self, conn: psycopg.Connection[Any]) -> None:
        """Refuse to work on an index rebuilt (by reindex) since this store opened.

        FOR SHARE makes a concurrent reindex wait for this transaction, so a
        note can't slip in with the old embedder after the check.
        """
        current = conn.execute(
            "SELECT embedding_provider, embedding_model, embedding_dim, fts_language"
            " FROM meta FOR SHARE"
        ).fetchone()
        if current != self._index_settings:
            raise SchemaMismatch(
                "The database was reindexed with different settings since this server"
                " started. Restart it with the settings it was reindexed with."
            )

    def is_healthy(self) -> bool:
        """Whether the database answers; for load balancer health checks."""
        try:
            with self._pool.connection(timeout=5) as conn:
                conn.execute("SELECT 1")
        except Exception:
            return False
        return True

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
        [embedding] = self._embedder.embed([_embedding_text(title, body)], "document")
        with self._pool.connection() as conn, conn.transaction():
            self._ensure_current(conn)
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
        candidates = max(limit * 5, 40)
        with self._pool.connection() as conn, conn.transaction():
            self._ensure_current(conn)
            # The HNSW index otherwise stops after ef_search (default 40) rows,
            # *then* applies the status/tag filters, silently dropping matches.
            # Iterative scans keep walking the graph until enough rows pass.
            conn.execute(
                "SELECT set_config('hnsw.iterative_scan', 'strict_order', true),"
                " set_config('hnsw.ef_search', %s, true)",
                (str(candidates),),
            )
            rows = conn.execute(
                _SEARCH_SQL,
                {
                    "query": query,
                    "statuses": statuses,
                    "tags": normalize_tags(tags or []),
                    "embedding": _vector_literal(embedding),
                    "lang": self._fts_language,
                    "candidates": candidates,
                    "min_similarity": self._min_similarity,
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
      AND 1 - (embedding <=> %(embedding)s::vector) >= %(min_similarity)s
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
