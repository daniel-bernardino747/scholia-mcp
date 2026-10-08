-- The embedding column and its HNSW index are not created here: their
-- dimension depends on the configured embedder, so they are added on first
-- boot (and rebuilt by `reindex`). See store.py.

CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS unaccent;

CREATE TABLE notes (
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    title        text NOT NULL,
    body         text NOT NULL,
    tags         text[] NOT NULL DEFAULT '{}',
    sources      jsonb NOT NULL DEFAULT '[]',
    origin_agent text NOT NULL,
    created_at   timestamptz NOT NULL DEFAULT now(),
    supersedes   uuid REFERENCES notes (id),
    status       text NOT NULL DEFAULT 'active'
                 CHECK (status IN ('active', 'superseded', 'archived')),
    tsv          tsvector NOT NULL
);

CREATE INDEX notes_tsv_idx ON notes USING gin (tsv);
CREATE INDEX notes_tags_idx ON notes USING gin (tags);
CREATE INDEX notes_status_idx ON notes (status);

-- Single row describing how `embedding` and `tsv` were computed.
CREATE TABLE meta (
    singleton          boolean PRIMARY KEY DEFAULT true CHECK (singleton),
    embedding_provider text NOT NULL,
    embedding_model    text NOT NULL,
    embedding_dim      integer NOT NULL,
    fts_language       text NOT NULL
);
