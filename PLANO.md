# scholia-mcp — plano

Segundo cérebro open source para agentes. Decidido em sessões de grilling em 2026-10-08. Ainda não construído.

- Repo: `daniel-bernardino747/scholia-mcp` (público) · Pacote PyPI: `scholia-mcp` (livre em 2026-10-08) · Licença: **MIT**
- Nome: *scholia* = comentários nas margens de manuscritos. `marginalia` descartado (colide com MarginaliaSearch e com shenmintao/marginalia, PKM com LLM). `scholia` no PyPI pertence ao WDscholia (Wikidata, outro nicho), aceitável.

## Objetivo

Guardar conhecimento das conversas com agentes (conclusões, dados, dúvidas, evolução de opiniões) e recuperá-lo em conversas novas. Hoje toda conversa recomeça do zero. Qualquer pessoa pode subir a própria instância.

## Decisões

| # | Tema | Decisão |
|---|---|---|
| 1 | Onde | claude.ai (principal) + Claude Code, via **um servidor MCP remoto**. Conector cadastrado no claude.ai já aparece no Claude Code (`claude_ai_*`). Qualquer cliente MCP serve. |
| 2 | O que salva | **Notas destiladas** escritas pelo agente (tema, conclusões, dados com fontes, posições, perguntas em aberto). Não transcrições. |
| 3 | Quando salva | **Agente sugere, usuário confirma** (pode editar antes). "Salva isso" manual também vale. |
| 4 | Quando busca | **Proativa**: ao entrar em assunto substantivo, busca antes de responder e **cita** a nota usada. |
| 5 | Mudança de ideia | **Append com vínculo**: nota nova com `supersedes: <id>`; a antiga fica `superseded` mas consultável. Busca prioriza `active`. |
| 6 | Auth *(revisado, #14)* | `AUTH_MODE=github` (OAuth, allowlist `ALLOWED_GITHUB_USERS`) ou `AUTH_MODE=bearer` (token fixo). **Fail-closed**: sem allowlist/token, o servidor não sobe. Cada deployer cria o próprio OAuth App. |
| 7 | Stack | **Python + FastMCP** (GitHub OAuth provider embutido). |
| 8 | Busca *(revisado, #15/#16)* | Busca híbrida: **pgvector (HNSW)** + **full-text Postgres** com `unaccent`. Embeddings plugáveis `EMBEDDING_PROVIDER=voyage|openai|ollama` (padrão no template: Voyage `voyage-3.5-lite`). Dimensão gravada no banco; servidor recusa subir se divergir; trocar provedor/idioma → comando `reindex`. `FTS_LANGUAGE` configurável (padrão `english`; template do Daniel: `portuguese`). |
| 9 | Organização | **Tags livres com reaproveitamento** via `list_tags`; normalização de acento/caixa. |
| 10 | Ferramentas | `search_notes`, `save_note`, `get_note`, `list_tags`, `archive_note`. **Sem delete** via MCP. |
| 11 | Memória nativa | Memória nativa do cliente = *como trabalhar comigo*. scholia = *conhecimento*. Regra explícita nas instruções. |
| 12 | Backup/portabilidade *(revisado, #17)* | Comandos **`export`** e **`import`** em Markdown com frontmatter (formato portátil oficial; import recalcula embeddings). Destino Git **opcional** (`EXPORT_GIT_REPO` + token) via cron; desligado se não configurado. Backups nativos do host continuam. |
| 13 | Tenancy | **Single-tenant**: uma instância por pessoa, sem `owner_id`. |
| 16 | Idioma | Código, campos, descrições das ferramentas e README em **inglês**. Instruções em **`en` e `pt-BR`**. Notas ficam no idioma da conversa. |
| 18 | Licença | **MIT**. |

## Esquema da nota

`id, title, body (markdown), tags[], sources[], origin_agent (claude.ai | claude-code | …), created_at, supersedes, status (active | superseded | archived), embedding vector(N), tsv tsvector`

Tabela de metadados: `embedding_provider, embedding_model, embedding_dim, fts_language`.

## Configuração (env)

`DATABASE_URL`, `AUTH_MODE`, `ALLOWED_GITHUB_USERS`, `GITHUB_CLIENT_ID`, `GITHUB_CLIENT_SECRET`, `BEARER_TOKEN`, `BASE_URL`, `EMBEDDING_PROVIDER`, `EMBEDDING_MODEL`, `VOYAGE_API_KEY` / `OPENAI_API_KEY` / `OLLAMA_URL`, `FTS_LANGUAGE`, `EXPORT_GIT_REPO`, `EXPORT_GIT_TOKEN`.

## Peças a construir

1. Servidor MCP (FastMCP) com as 5 ferramentas + modos de auth
2. Schema Postgres + pgvector (HNSW, GIN), migração inicial, checagem de dimensão
3. Adaptadores de embedding (voyage, openai, ollama)
4. CLI: `serve`, `reindex`, `export`, `import`
5. Cron opcional de export → Git
6. Deploy: `Dockerfile`, `docker-compose.yml` (Postgres+pgvector), **template 1-clique do Railway**
7. Instruções para colar nas preferências (`en`, `pt-BR`)
8. README (setup do GitHub OAuth App, Railway, docker-compose, Claude Code), LICENSE MIT

## Adiado

- Importador do export de histórico do claude.ai
- Outros provedores de OAuth (contribuição futura)
- Multi-tenant (descartado por ora)

## Avaliação de soluções prontas (pesquisa 2026-10-08)

Nenhum projeto pronto cobre o plano inteiro (pgvector + híbrida PT + OAuth claude.ai + supersedes + self-host).

| Opção | Atende | Não atende |
|---|---|---|
| **Basic Memory Cloud** (pago, ~US$15/mês, não verificado; trial 7d) — https://docs.basicmemory.com/guides/cloud | Conector claude.ai com OAuth pronto, web/mobile/Claude Code, Markdown exportável | Hospedado por terceiro; sem `supersedes`/arquivamento; agente pode editar/apagar |
| **mcp-memory-service** (doobidoo, ~2k★, Apache-2.0) — https://github.com/doobidoo/mcp-memory-service | OAuth 2.0 remoto p/ claude.ai e ChatGPT, tags, agent-id, Docker | Sem Postgres, embeddings ONNX locais (PT não documentado), memórias curtas, sem supersedes |
| **Memory Vault** (MihaiBuilds) — https://claudemarketplaces.com/mcp/mihaibuilds/memory-vault | Postgres + pgvector + híbrida, Docker | Sem OAuth p/ claude.ai |
| **Second Brain** (rahilp) — https://mcp.so/server/second-brain/rahilp | Notas + busca semântica, remoto | Cloudflare, embedding só inglês, sem OAuth documentado |
| Referência: blog FastMCP + pgvector — https://blog.dpinkerton.com/posts/self-hosted-mcp-memory-server/ | Mesma stack | Bearer, só Claude Code. Dica: **HNSW** (IVFFlat falha em tabela vazia) |

**Conclusão:** construir o próprio, open source.
