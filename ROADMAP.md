# scholia-mcp — roadmap

Etapas na ordem de construção. Decisões e motivos estão em [PLANO.md](PLANO.md) — não reabrir sem motivo novo.
Cada etapa termina com um critério "pronto quando" verificável.

---

## Etapa 1 — Núcleo local (bearer + save/search)

- [x] Projeto Python: `pyproject.toml` (uv), pacote `scholia_mcp/`, Python 3.12+
- [x] Dependências: `fastmcp`, `psycopg[binary,pool]` (síncrono: psycopg async não roda no event loop padrão do Windows), `httpx`, `pydantic-settings` — sem o pacote `pgvector`: vetores vão como literal `::vector`
- [x] `config.py`: lê env (ver lista em PLANO.md); **fail-closed** — sem `BEARER_TOKEN` em `AUTH_MODE=bearer`, aborta
- [x] `docker-compose.yml`: imagem `pgvector/pgvector:pg17` + o servidor
- [x] Migração inicial (SQL puro, versionada):
  - [x] `CREATE EXTENSION vector; CREATE EXTENSION unaccent;`
  - [x] tabela `notes` (`id uuid, title, body, tags text[], sources jsonb, origin_agent, created_at, supersedes uuid null, status`, `embedding vector(N)`, `tsv tsvector`)
  - [x] tabela `meta` (`embedding_provider, embedding_model, embedding_dim, fts_language`)
  - [x] índice **HNSW** em `embedding` (não IVFFlat — falha em tabela vazia), GIN em `tsv` e em `tags`
  - [x] `tsv` = `to_tsvector(fts_language, unaccent(title || ' ' || body))`, calculado no INSERT (não coluna gerada: `unaccent` não é imutável e o `reindex` precisa recalcular)
  - [x] coluna `embedding` + índice HNSW criados no primeiro boot com a dimensão do embedder (a migração não sabe N)
- [x] Checagem no boot: dimensão/provedor/idioma do env == `meta`; se divergir, recusa subir e manda rodar `reindex`
- [x] Um adaptador de embedding (Voyage) atrás de interface `embed(texts, input_type) -> list[vector]`
- [x] Ferramenta `save_note(title, body, tags, sources, origin_agent, supersedes?)` — se `supersedes`, marca a antiga como `superseded` na mesma transação
- [x] Ferramenta `search_notes(query, tags?, include_superseded=false, limit=8)` — híbrida: ranking vetorial + `ts_rank`, combinados por **RRF** (reciprocal rank fusion); retorna id, título, trecho, tags, data, status
- [x] Auth `bearer`
- [x] Testes de integração contra Postgres real (docker): salvar, buscar por sentido, buscar por termo exato, supersede

- [x] `MIN_SIMILARITY`: piso de similaridade cosseno para a parte vetorial da busca (termo exato sempre passa). Padrão 0 = desligado
- [x] Calibrar `MIN_SIMILARITY` com scores reais do Voyage (2026-10-09, `voyage-3.5-lite`, 5 notas pt-BR): nota certa 0,44–0,63; melhor nota sem relação 0,34–0,52 — as faixas se sobrepõem, então o padrão fica **0** (desligado). Reavaliar com mais notas ou com um corte relativo ao melhor score

*Validado em 2026-10-09 no docker compose com Voyage real: 3/3 buscas por sinônimo e 3/3 por sigla com a nota certa em 1º; Claude Code conectado via `claude mcp add`.*

**Pronto quando:** `docker compose up`, conectar o Claude Code via `claude mcp add --transport http ... --header "Authorization: Bearer ..."`, salvar uma nota e achá-la por sinônimo e por sigla.

---

## Etapa 2 — GitHub OAuth + deploy no Railway (uso real começa aqui)

- [x] `AUTH_MODE=github` com o provider GitHub do FastMCP; checa login contra `ALLOWED_GITHUB_USERS`; fail-closed se lista vazia. Aceita também IDs numéricos (mais seguro: login pode ser renomeado e registrado por outra pessoa); escopo `read:user`; estado OAuth criptografado no Postgres (`oauth_state`) para sobreviver a redeploys
- [x] `BASE_URL` para callbacks OAuth
- [x] `Dockerfile` enxuto (sem modelos locais)
- [x] Criar OAuth App no GitHub (callback = `BASE_URL` + rota do FastMCP)
- [x] Railway: projeto com Postgres (com pgvector) + serviço do servidor; env com `FTS_LANGUAGE=portuguese`
- [ ] Ativar backups nativos do Postgres no Railway
- [x] claude.ai → Settings → Connectors → adicionar custom connector com a URL `/mcp`; fazer login
- [ ] Conferir que aparece no Claude Code como `claude_ai_*`
- [x] Rascunho das instruções pt-BR (`instructions/pt-BR.md`; testado: com as instruções, o Claude busca no scholia e cita a nota) nas preferências pessoais do claude.ai (sugerir salvar, busca proativa, citar nota, reaproveitar tags, divisão com memória nativa)

*Deploy em 2026-10-09: https://scholia-production.up.railway.app (template pgvector `3jJFCA`). Login OAuth + `save_note` pelo claude.ai funcionando; na primeira busca o Claude usou a memória nativa em vez do scholia, sem instruções nas preferências. Com `instructions/pt-BR.md` nas preferências, numa conversa nova na web, ele buscou sozinho e citou a nota. Falta conferir no celular.*

**Pronto quando:** numa conversa nova no claude.ai (web e celular), o Claude busca sozinho num assunto já salvo e cita a nota.

---

## Etapa 3 — Ferramentas restantes + embeddings plugáveis

- [ ] `get_note(id)` — nota completa, incluindo cadeia de `supersedes` (anteriores e sucessora)
- [ ] `list_tags()` — tags com contagem, normalizadas (minúsculas, sem acento)
- [ ] `archive_note(id, reason?)` — status `archived`, some das buscas; reversível via banco/CLI
- [ ] Descrições das ferramentas em inglês, escritas para o modelo (quando chamar, o que passar)
- [ ] Adaptadores `openai` e `ollama`; `EMBEDDING_PROVIDER` / `EMBEDDING_MODEL`
- [ ] CLI `scholia reindex` — recalcula embeddings e `tsv`, recria coluna/índice com a nova dimensão, atualiza `meta`
- [ ] Testes por adaptador (com fake para CI)

**Pronto quando:** trocar Voyage → OpenAI, rodar `reindex`, e a busca continuar funcionando.

---

## Etapa 4 — Export / import em Markdown + cron opcional

- [ ] Formato: um `.md` por nota, frontmatter YAML (`id, title, tags, sources, origin_agent, created_at, supersedes, status`), corpo = `body`
- [ ] `scholia export <dir>` (todas as notas, inclusive superseded/archived, para preservar histórico)
- [ ] `scholia import <dir>` — idempotente por `id`, recalcula embeddings; aceita `.md` sem frontmatter completo (ex.: Obsidian) gerando id
- [ ] Teste de ida e volta: export → banco vazio → import → mesmas notas
- [ ] Cron opcional: se `EXPORT_GIT_REPO` + `EXPORT_GIT_TOKEN`, exporta, commit e push; senão não faz nada
- [ ] Serviço de cron no Railway apontando para o repo privado de backup

**Pronto quando:** o repo privado de backup recebe commits diários com as notas legíveis.

---

## Etapa 5 — Open source

- [ ] `instructions/en.md` e `instructions/pt-BR.md` (versão final, testada na etapa 2)
- [ ] README em inglês: o que é, por que, setup (GitHub OAuth App passo a passo, Railway, docker-compose, Claude Code, bearer), env vars, reindex, export/import, segurança (fail-closed, sem delete via MCP)
- [ ] Template 1-clique do Railway (Postgres+pgvector + servidor + cron opcional)
- [ ] CI (GitHub Actions): lint + testes com Postgres em service container
- [ ] `CONTRIBUTING.md` curto
- [ ] Criar repo público `daniel-bernardino747/scholia-mcp` e push
- [ ] Publicar `scholia-mcp` no PyPI (opcional)

**Pronto quando:** alguém sem contexto sobe a própria instância só seguindo o README.

---

## Depois (fora do escopo atual)

- Importador do export de histórico do claude.ai
- Outros provedores OAuth (Google etc.) via contribuição
- Ligar outros agentes (ChatGPT, Cursor…) — já suportado por MCP + `origin_agent`
