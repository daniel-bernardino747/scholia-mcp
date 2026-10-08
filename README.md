# scholia-mcp

Self-hosted second brain for AI agents: distilled notes from your conversations, saved and recalled through a remote MCP server (Postgres + pgvector, hybrid search).

> Status: planning. See [ROADMAP.md](ROADMAP.md) and [PLANO.md](PLANO.md) (decisions, in Portuguese).

License: MIT.

## Run locally (early)

Requires Docker and [uv](https://docs.astral.sh/uv/).

```sh
cp .env.example .env          # set BEARER_TOKEN and VOYAGE_API_KEY
docker compose up -d --build  # Postgres + pgvector on :54330, server on :8000
claude mcp add --transport http scholia http://localhost:8000/mcp \
  --header "Authorization: Bearer <BEARER_TOKEN>"
```

The server refuses to start on an incomplete configuration, and refuses to
start against a database indexed with a different embedding model, dimension or
`FTS_LANGUAGE` (rebuilding it with `reindex` is on the roadmap).

## Development

```sh
docker compose up -d db   # tests use the scholia_test database it creates
uv run pytest
uv run pyright && uv run ruff check
```
