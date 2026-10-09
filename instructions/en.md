# scholia — instructions for your claude.ai preferences

Paste the block below into **claude.ai → Settings → Profile → "What personal preferences
should Claude consider in responses?"** (or into a project's instructions).

---

I have a personal knowledge base in the **scholia** connector (tools `search_notes` and `save_note`). It holds what I concluded in earlier conversations: decisions, data with sources, opinions and open questions.

**scholia vs. built-in memory.** Built-in memory is for *how to work with me* (style, format, personal context). scholia is for *what I know and decided*. For questions about my decisions, conclusions, opinions or data, scholia is the primary source — check it even if built-in memory seems to have the answer.

**Search before answering.** When the topic is substantive (a project, a decision, a subject I study, "what did I decide/think about X"), call `search_notes` before answering, with a short natural-language query. If something relevant comes up, use it and **cite the note** (title and date). If nothing does, say there's no note on it. Don't search for small talk.

**Suggest saving, don't save on your own.** When a conversation reaches a conclusion worth keeping, offer to save it and show the draft note (title, distilled Markdown body, tags, sources). Only call `save_note` after I confirm or edit it. If I say "save this", save it directly. Notes are distilled: conclusions, figures with sources, positions and open questions — not a transcript. Write in the language of the conversation.

**Tags.** Reuse tags that appear in search results before creating new ones. Short, lowercase.

**Changing my mind.** If a new conclusion replaces an existing note, save the new one with `supersedes` set to the old note's id instead of duplicating it.

**Origin.** Set `origin_agent` to `claude.ai` (or `claude-code` when in Claude Code).
