"""The MCP server: tool definitions over a NoteStore.

Tool docstrings and parameter descriptions are what the model reads to decide
when to call a tool and what to pass; they are written for it.
"""

from typing import Annotated
from uuid import UUID

import anyio
from fastmcp import FastMCP
from fastmcp.server.auth import AuthProvider
from pydantic import BaseModel, Field
from starlette.requests import Request
from starlette.responses import JSONResponse

from scholia_mcp.store import Note, NoteDetail, NoteStore, SearchHit, TagCount

INSTRUCTIONS = """\
scholia is the user's long-term knowledge base: distilled notes from their past
conversations with AI agents (decisions, conclusions, data with sources,
positions, open questions). It is the primary source for what the user knows
and has decided; built-in memory is for how to work with them.

Search it before answering on a substantive topic, and whenever the user asks
what they decided, concluded or thought about something. Cite the notes you
use (title and date). Suggest saving a note when a conversation reaches a
conclusion worth keeping, show the draft, and save only after the user
confirms or says "save this".
"""


class SearchResults(BaseModel):
    results: list[SearchHit]


class TagList(BaseModel):
    tags: list[TagCount]


def create_server(store: NoteStore, auth: AuthProvider | None = None) -> FastMCP:
    mcp = FastMCP("scholia", instructions=INSTRUCTIONS, auth=auth)

    @mcp.tool
    def save_note(
        title: Annotated[
            str,
            Field(description="Short, specific title that names the topic and the conclusion."),
        ],
        body: Annotated[
            str,
            Field(
                description="The distilled note in Markdown: conclusions, figures with their"
                " sources, positions and open questions. Not a transcript. In the language"
                " of the conversation."
            ),
        ],
        tags: Annotated[
            list[str],
            Field(
                description="A few topic tags. Reuse existing ones (see list_tags or tags in"
                " search results) before inventing new ones. Normalized to lowercase"
                " without accents."
            ),
        ],
        sources: Annotated[
            list[str],
            Field(description="URLs or citations backing the note's data. Empty if none."),
        ],
        origin_agent: Annotated[
            str,
            Field(description="Where the note comes from: 'claude.ai', 'claude-code', etc."),
        ],
        supersedes: Annotated[
            UUID | None,
            Field(
                description="When this note replaces an earlier one (the user changed their"
                " mind or the conclusion was revised), the earlier note's id. It becomes"
                " 'superseded': kept, but out of default search results."
            ),
        ] = None,
    ) -> Note:
        """Save a distilled note to the user's knowledge base.

        Call it only after the user confirmed the draft, or asked you to save.
        To revise an existing note, pass `supersedes` instead of saving a duplicate.
        """
        return store.save(title, body, tags, sources, origin_agent, supersedes)

    @mcp.tool
    def search_notes(
        query: Annotated[
            str,
            Field(
                description="What to look for, in natural language. Matches by meaning and"
                " by exact terms or acronyms."
            ),
        ],
        tags: Annotated[
            list[str] | None,
            Field(description="Only return notes carrying at least one of these tags."),
        ] = None,
        include_superseded: Annotated[
            bool,
            Field(
                description="Also return notes replaced by newer ones, e.g. to show how the"
                " user's view evolved."
            ),
        ] = False,
        limit: Annotated[int, Field(ge=1, le=50, description="Maximum results.")] = 8,
    ) -> SearchResults:
        """Search the user's knowledge base, best matches first.

        Use it before answering on a substantive topic and whenever the user asks
        what they decided or thought. Results are excerpts; call get_note for the
        full text. Archived notes never appear.
        """
        return SearchResults(results=store.search(query, tags, include_superseded, limit))

    @mcp.tool
    def get_note(
        id: Annotated[UUID, Field(description="The note's id, from search_notes.")],
    ) -> NoteDetail:
        """Read a note in full, with its sources and version history.

        `previous_versions` are the notes it replaced and `newer_versions` the
        ones that replaced it, oldest first. The current view is the one with
        status 'active' (archived versions were withdrawn): prefer it when answering.
        """
        return store.get(id)

    @mcp.tool
    def list_tags() -> TagList:
        """List the tags used by current notes, most used first.

        Call it before saving a note to reuse existing tags.
        """
        return TagList(tags=store.list_tags())

    @mcp.tool
    def archive_note(
        id: Annotated[UUID, Field(description="The note's id.")],
        reason: Annotated[
            str | None, Field(description="Why it is archived, e.g. 'duplicate', 'wrong'.")
        ] = None,
    ) -> Note:
        """Archive a note so it no longer appears in any search.

        Only when the user asks for it (a mistaken or useless note). A note that
        was replaced by a newer conclusion should be superseded via save_note
        instead. Archived notes stay readable with get_note; there is no delete.
        """
        return store.archive(id, reason)

    @mcp.custom_route("/health", methods=["GET"])
    async def health(request: Request) -> JSONResponse:
        # Public (outside /mcp auth) and says nothing beyond up/down. The check
        # blocks on the database, so it runs in a worker thread, not the event loop.
        if await anyio.to_thread.run_sync(store.is_healthy):
            return JSONResponse({"status": "ok"})
        return JSONResponse({"status": "unavailable"}, status_code=503)

    return mcp
