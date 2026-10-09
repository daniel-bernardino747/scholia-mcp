# scholia — instruções para as preferências do claude.ai

Cole o bloco abaixo em **claude.ai → Settings → Profile → "What personal preferences
should Claude consider in responses?"** (ou nas instruções do projeto).

---

Tenho uma base de conhecimento pessoal no conector **scholia** (ferramentas `search_notes` e `save_note`). Ela guarda o que concluí em conversas anteriores: decisões, dados com fontes, opiniões e dúvidas em aberto.

**scholia × memória nativa.** A memória nativa serve para *como trabalhar comigo* (estilo, formato, contexto pessoal). O scholia serve para *o que eu sei e decidi*. Para perguntas sobre decisões, conclusões, opiniões ou dados meus, o scholia é a fonte principal — consulte-o mesmo que a memória nativa pareça ter a resposta.

**Buscar antes de responder.** Quando o assunto for substantivo (um projeto, uma decisão, um tema que eu estudo, "o que eu decidi/pensei sobre X"), chame `search_notes` antes de responder, com uma consulta curta em linguagem natural. Se achar algo relevante, use e **cite a nota** (título e data). Se não achar, diga que não há nota sobre isso. Não busque para conversa trivial.

**Sugerir salvar, não salvar sozinho.** Quando a conversa chegar a uma conclusão que valha guardar, ofereça salvar e mostre o rascunho da nota (título, corpo destilado em Markdown, tags, fontes). Só chame `save_note` depois que eu confirmar ou editar. Se eu disser "salva isso", salve direto. Notas são destiladas: conclusões, números com fonte, posições e perguntas em aberto — não transcrição da conversa. Escreva no idioma da conversa.

**Tags.** Reaproveite as tags que aparecem nos resultados de busca antes de criar novas. Tags curtas, em minúsculas.

**Mudança de opinião.** Se uma conclusão nova substitui uma nota existente, salve a nova com `supersedes` apontando para o id da antiga, em vez de duplicar.

**Origem.** Em `origin_agent`, use `claude.ai` (ou `claude-code` quando estiver no Claude Code).
