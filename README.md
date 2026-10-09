# scholia-mcp

A self-hosted second brain for AI agents. Every conversation with Claude starts from zero; scholia gives it a memory of what you've *concluded*. It is a remote MCP server where the agent saves distilled notes from your conversations (decisions, data with sources, positions, open questions) and searches them before answering in new ones.

*Scholia* are the comments scholars wrote in the margins of manuscripts.

- **Distilled notes, not transcripts.** The agent drafts a note when a conversation reaches a conclusion; you confirm before it's saved.
- **Proactive recall.** On a substantive topic, the agent searches first and cites the note it used.
- **Opinions evolve.** A new note can *supersede* an old one; the old one stays, marked `superseded`, out of default results but searchable.
- **Hybrid search.** pgvector (meaning) and Postgres full-text (exact terms and acronyms) are fused with reciprocal rank fusion, accent-insensitive, in your language.
- **Yours.** One instance per person on your own Postgres. No delete over MCP.

Works with claude.ai (web and mobile, as a custom connector), Claude Code, and any MCP client.

> Status: in daily use by its author. Next up: `get_note`, `list_tags`, `archive_note`, an Ollama adapter, and Markdown export/import. See [ROADMAP.md](ROADMAP.md) (in Portuguese).

## How it works

| Tool | What it does |
|---|---|
| `save_note(title, body, tags, sources, origin_agent, supersedes?)` | Saves a note. With `supersedes`, the referenced note becomes `superseded` in the same transaction. Tags are normalized (lowercase, no accents). |
| `search_notes(query, tags?, include_superseded=false, limit=8)` | Hybrid search. Returns id, title, excerpt, tags, date and status. |

Notes live in one Postgres table with an HNSW vector index and a GIN full-text index. The embedding model, its dimension and the full-text language are recorded in the database; the server refuses to start if your configuration no longer matches them (see [Changing the embedding model or language](#changing-the-embedding-model-or-language)).

## Deploy on Railway

You need accounts on [Railway](https://railway.com), GitHub, and one embedding provider. It takes about 15 minutes.

### 1. Get an embedding API key

Pick one:

- **Voyage AI** (default, good multilingual quality): create a key at [dashboard.voyageai.com](https://dashboard.voyageai.com) → *API Keys*. It starts with `pa-`. Keys created through MongoDB Atlas only work against a different endpoint and are not supported yet. Without a payment method on file, Voyage limits you to about 3 requests per minute, which you'll hit; adding one keeps the free tokens.
- **OpenAI**: create a key at [platform.openai.com/api-keys](https://platform.openai.com/api-keys).

### 2. Create the Railway project

1. Fork this repository (so you control when you update).
2. In Railway, create a new project and add the **pgvector** template (search "pgvector"; the one by Railway staff is `3jJFCA`). Railway's default Postgres does **not** include pgvector.
3. Add a service from your fork (*New → GitHub Repo*). Railway builds it with the included `Dockerfile`.
4. In that service's *Settings → Networking*, generate a public domain on port **8000**. Note the URL, e.g. `https://scholia-production.up.railway.app`.
5. In the pgvector service, turn on **Backups**.

### 3. Create a GitHub OAuth App

claude.ai connectors log in with OAuth; scholia uses GitHub as the identity provider and only lets in the accounts you list.

1. Go to [github.com/settings/applications/new](https://github.com/settings/applications/new).
2. **Homepage URL**: your Railway URL. **Redirect URI** (called *Authorization callback URL* in older forms): your Railway URL + `/auth/callback`. Leave *wildcard matching* and *device flow* off.
3. Register it, copy the **Client ID**, and generate a **client secret**.
4. Find your numeric GitHub ID: `gh api users/<your-login> --jq .id` (or open `https://api.github.com/users/<your-login>`).

### 4. Set the variables

In the server service's *Variables*:

| Variable | Value |
|---|---|
| `DATABASE_URL` | `${{pgvector.DATABASE_URL_PRIVATE}}` |
| `AUTH_MODE` | `github` |
| `ALLOWED_GITHUB_USERS` | your numeric GitHub ID (comma-separate several) |
| `GITHUB_CLIENT_ID` / `GITHUB_CLIENT_SECRET` | from step 3 |
| `BASE_URL` | your Railway URL, `https://…` |
| `PORT` | `8000` |
| `EMBEDDING_PROVIDER` | `voyage` or `openai` |
| `VOYAGE_API_KEY` or `OPENAI_API_KEY` | from step 1 |
| `FTS_LANGUAGE` | the language you write in, e.g. `english`, `portuguese`, `spanish` |

Deploy. The logs should end with `Uvicorn running on http://0.0.0.0:8000`. If a variable is missing, the server says which and refuses to start.

### 5. Connect claude.ai

1. claude.ai → *Settings → Connectors → Add custom connector*. URL: your Railway URL + `/mcp`. Leave the advanced OAuth fields empty.
2. *Connect*: approve scholia's consent screen, then GitHub's (it asks only to read your profile).
3. Paste the instructions from [`instructions/en.md`](instructions/en.md) (or [`pt-BR.md`](instructions/pt-BR.md)) into *Settings → Profile → personal preferences*. Without them Claude tends to answer from its built-in memory instead of searching scholia.

Open a new conversation and try: *"save a note that I chose Railway to host scholia"*, then in another one: *"what did I decide about hosting?"*.

### Claude Code

Connectors added on claude.ai show up in Claude Code automatically (as `claude_ai_scholia`) when you're logged in with the same account. To connect Claude Code directly, see [Run locally](#run-locally).

## Run locally

Requires Docker and [uv](https://docs.astral.sh/uv/).

```sh
cp .env.example .env          # set BEARER_TOKEN and your embedding key
docker compose up -d --build  # Postgres + pgvector on :54330, server on :8000
claude mcp add --transport http scholia http://localhost:8000/mcp \
  --header "Authorization: Bearer <BEARER_TOKEN>"
```

`AUTH_MODE=bearer` accepts one shared token. Use it locally or for clients that can't do OAuth; claude.ai connectors need `AUTH_MODE=github`.

## Configuration

All configuration is through environment variables; see [`.env.example`](.env.example).

| Variable | Default | |
|---|---|---|
| `DATABASE_URL` | — | Postgres with the `vector` and `unaccent` extensions available. |
| `AUTH_MODE` | `bearer` | `bearer` or `github`. |
| `BEARER_TOKEN` | — | Required in `bearer` mode. |
| `ALLOWED_GITHUB_USERS` | — | Required in `github` mode. Numeric IDs (recommended: a login can be renamed and re-registered by someone else) or logins, comma-separated. |
| `GITHUB_CLIENT_ID`, `GITHUB_CLIENT_SECRET`, `BASE_URL` | — | Required in `github` mode. |
| `EMBEDDING_PROVIDER` | `voyage` | `voyage` or `openai`. |
| `EMBEDDING_MODEL` | per provider | `voyage-3.5-lite` / `text-embedding-3-small`. Also: `voyage-3.5`, `voyage-3-large`, `voyage-multilingual-2`, `text-embedding-3-large` (shortened to 1536 dims). |
| `VOYAGE_API_KEY` / `OPENAI_API_KEY` | — | For the chosen provider. |
| `FTS_LANGUAGE` | `english` | Any Postgres text search configuration. |
| `MIN_SIMILARITY` | `0` | Cosine similarity a note needs to be returned without a keyword match. `0` disables it; in tests with `voyage-3.5-lite`, related and unrelated notes overlapped between 0.34 and 0.52, so calibrate on your own notes before raising it. |
| `HOST`, `PORT` | `0.0.0.0`, `8000` | |

## Changing the embedding model or language

Vectors from different models (or the same model at different dimensions) can't be compared, and full-text vectors depend on the language. So after changing `EMBEDDING_PROVIDER`, `EMBEDDING_MODEL` or `FTS_LANGUAGE`, the server refuses to start until you rebuild the index:

```sh
uv run scholia-mcp reindex
```

It needs the new variables plus a `DATABASE_URL` you can reach from where you run it. On Railway, copy the service's variables into a local file, replace `DATABASE_URL` with the pgvector service's public `DATABASE_URL`, and run `uv run --env-file <that file> scholia-mcp reindex`.

Reindex computes every embedding first, then swaps column, index and full-text vectors in a single transaction: if the embedding API fails, nothing changes. A server still running with the old settings refuses to save or search once the index has been rebuilt; restart it with the new ones.

## Security

- **Fail-closed.** Missing auth settings, an empty allowlist, a missing API key or an index built with other settings all stop the server from starting.
- **Allowlist on every request.** In `github` mode, each request re-checks the GitHub account against `ALLOWED_GITHUB_USERS`; removing an entry revokes access immediately. Only the `read:user` scope is requested.
- **OAuth state** (client registrations, upstream tokens) is stored encrypted in Postgres, with a key derived from the GitHub client secret. Rotating the secret logs every client out.
- **No delete over MCP.** Agents can save and supersede notes, never remove them.
- One instance per person: there is no multi-user separation inside a database.

## Development

```sh
docker compose up -d db   # also creates the scholia_test database the tests use
uv run pytest
uv run pyright && uv run ruff check && uv run ruff format --check
```

Tests run against a real Postgres with a deterministic fake embedder; no API keys needed. See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

[MIT](LICENSE).
