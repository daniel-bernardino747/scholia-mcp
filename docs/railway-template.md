# Railway template

Maintainer notes for the one-click template (draft code `YCIHYg`). The draft was
generated from a clean project (`railway templates create`), which keeps
reference values but drops literal ones, so the defaults below must be set in
the template editor before publishing.

## Template editor checklist

1. Rename the template from `scholia-template` to **scholia**.
2. Rename the server service from `scholia-mcp` to **scholia** (optional).
3. Server service variables:

| Variable | Default | Optional | Description |
|---|---|---|---|
| `DATABASE_URL` | `${{pgvector.DATABASE_URL_PRIVATE}}` | no | Postgres with pgvector, over the private network. Leave as is. |
| `BASE_URL` | `https://${{RAILWAY_PUBLIC_DOMAIN}}` | no | Public URL of this service, used for OAuth callbacks. Leave as is. |
| `PORT` | `8000` | no | Port the server listens on; the public domain targets it. |
| `AUTH_MODE` | `github` | no | `github` (OAuth, needed for claude.ai) or `bearer` (one shared token). |
| `ALLOWED_GITHUB_USERS` | — | no | Your numeric GitHub ID (`https://api.github.com/users/<login>` → `id`). Comma-separate several. |
| `GITHUB_CLIENT_ID` | — | no | From a GitHub OAuth App whose Redirect URI is `<this service's URL>/auth/callback`. |
| `GITHUB_CLIENT_SECRET` | — | no | From the same OAuth App. |
| `EMBEDDING_PROVIDER` | `voyage` | no | `voyage` or `openai`. |
| `VOYAGE_API_KEY` | — | yes | Required when `EMBEDDING_PROVIDER=voyage`. |
| `OPENAI_API_KEY` | — | yes | Required when `EMBEDDING_PROVIDER=openai`. Add it in the editor; it isn't in the draft. |
| `FTS_LANGUAGE` | `english` | no | Postgres text search language of your notes, e.g. `portuguese`, `spanish`. |
| `MIN_SIMILARITY` | `0` | yes | Leave at 0 unless you've calibrated it. |

Mark `VOYAGE_API_KEY` as optional, since OpenAI users won't have one.

4. Check the public domain targets port **8000** and the pgvector volume is kept.

## Chicken-and-egg on first deploy

The GitHub OAuth App needs the service URL, which only exists after deploying.
Users can deploy with placeholder GitHub values (the server refuses to start,
saying which variable is wrong), copy the generated URL, create the OAuth App,
then set the real values and redeploy. The overview below says so.

## Publishing

```sh
railway templates publish YCIHYg --category AI/ML \
  --description "Self-hosted second brain for Claude and other AI agents, over MCP" \
  --readme-file docs/railway-template-overview.md
```

Then add the deploy button to the README:
`[![Deploy on Railway](https://railway.com/button.svg)](https://railway.com/deploy/YCIHYg)`
