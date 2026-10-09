# Contributing

Thanks for helping. scholia is small on purpose: one person's knowledge base, one Postgres, a handful of MCP tools.

## Setup

```sh
docker compose up -d db   # Postgres + pgvector on :54330, with a scholia_test database
uv sync
uv run pytest
```

No API keys are needed: tests use a deterministic fake embedder (`tests/conftest.py`) against a real Postgres. Point them elsewhere with `TEST_DATABASE_URL`.

## Before opening a pull request

```sh
uv run ruff check && uv run ruff format --check && uv run pyright && uv run pytest
```

CI runs the same commands.

## Guidelines

- **Test through public interfaces.** Tools are tested through FastMCP's in-memory client, configuration through `Settings`, boot behaviour through `open_store`, external APIs (embeddings, GitHub) with their HTTP faked. Avoid tests that reach into the database behind the tools' back.
- **Fail closed.** A configuration that would leave the server open, or silently produce wrong results, should stop it from starting with a message that says what to fix.
- **No destructive tools over MCP.** Agents can save and supersede notes, never delete them.
- **Index settings are recorded.** Anything that changes how `embedding` or `tsv` is computed must be recorded in `meta` and handled by `reindex`.
- New embedding providers go in `src/scholia_mcp/embeddings.py`, behind the `Embedder` protocol, with their dimension under pgvector's 2000-dim HNSW limit.
- Code, identifiers, tool descriptions and docs are in English.
- Design decisions and their reasons are in [PLANO.md](PLANO.md) (Portuguese); please open an issue before changing one.
