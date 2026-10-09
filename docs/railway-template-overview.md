# Deploy and Host scholia on Railway

scholia is a self-hosted second brain for AI agents. Claude (on claude.ai, mobile or Claude Code) saves distilled notes from your conversations — decisions, data with sources, positions, open questions — and searches them before answering in new ones, citing the note it used.

## About Hosting scholia

This template runs two services: Postgres with pgvector, and the scholia MCP server, built from [github.com/daniel-bernardino747/scholia-mcp](https://github.com/daniel-bernardino747/scholia-mcp). claude.ai connects to it as a custom connector and logs in with GitHub; only the GitHub accounts you list get in.

Before deploying, get an embedding API key from [Voyage AI](https://dashboard.voyageai.com) or OpenAI.

1. Deploy. Fill the GitHub fields with placeholders for now; the server will refuse to start and say which variable is missing.
2. Copy the service's public URL. Create a GitHub OAuth App at github.com/settings/applications/new with that URL as homepage and `<URL>/auth/callback` as Redirect URI.
3. Set `GITHUB_CLIENT_ID`, `GITHUB_CLIENT_SECRET` and `ALLOWED_GITHUB_USERS` (your numeric GitHub ID) and redeploy.
4. In claude.ai → Settings → Connectors, add a custom connector with `<URL>/mcp`, and paste the [preference instructions](https://github.com/daniel-bernardino747/scholia-mcp/tree/main/instructions) into your profile.

Turn on Backups for the pgvector service.

## Common Use Cases

- Keep what you concluded with Claude across conversations, on web, mobile and Claude Code
- Track how your opinions change: new notes supersede old ones without erasing them
- Search your notes by meaning and by exact terms or acronyms, in your own language

## Dependencies for scholia Hosting

- Postgres with the pgvector extension (included)
- A Voyage AI or OpenAI API key for embeddings
- A GitHub OAuth App for login

### Deployment Dependencies

- [scholia-mcp on GitHub](https://github.com/daniel-bernardino747/scholia-mcp)
- [Voyage AI API keys](https://dashboard.voyageai.com)
- [GitHub OAuth Apps](https://github.com/settings/developers)

## Why Deploy scholia on Railway?

Railway is a singular platform to deploy your infrastructure stack. Railway will host your infrastructure so you don't have to deal with configuration, while allowing you to vertically and horizontally scale it.

By deploying scholia on Railway, you are one step closer to supporting a complete full-stack application with minimal burden. Host your servers, databases, AI agents, and more on Railway.
