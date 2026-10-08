"""The MCP server: tool definitions over a NoteStore."""

import hmac
from typing import Annotated
from uuid import UUID

from fastmcp import FastMCP
from fastmcp.server.auth import AccessToken, AuthProvider, TokenVerifier
from pydantic import BaseModel, Field

from scholia_mcp.config import Settings
from scholia_mcp.store import Note, NoteStore, SearchHit

INSTRUCTIONS = """\
scholia is the user's long-term knowledge base: distilled notes from past
conversations (conclusions, data with sources, positions, open questions).
Search it before answering on a substantive topic and cite the notes you use.
Suggest saving a note when a conversation reaches a conclusion worth keeping;
save only after the user confirms.
"""


class SearchResults(BaseModel):
    results: list[SearchHit]


class StaticBearerVerifier(TokenVerifier):
    """Accepts exactly one shared token, compared in constant time."""

    def __init__(self, token: str):
        super().__init__()
        self._token = token.encode()

    async def verify_token(self, token: str) -> AccessToken | None:
        if not hmac.compare_digest(token.encode(), self._token):
            return None
        return AccessToken(token=token, client_id="bearer", scopes=[])


def build_auth(settings: Settings) -> AuthProvider:
    match settings.auth_mode:
        case "bearer":
            assert settings.bearer_token  # guaranteed by Settings
            return StaticBearerVerifier(settings.bearer_token)


def create_server(store: NoteStore, auth: AuthProvider | None = None) -> FastMCP:
    mcp = FastMCP("scholia", instructions=INSTRUCTIONS, auth=auth)

    @mcp.tool
    def save_note(
        title: Annotated[str, Field(description="Short, specific title for the note.")],
        body: Annotated[str, Field(description="Distilled note in Markdown.")],
        tags: Annotated[list[str], Field(description="Topic tags.")],
        sources: Annotated[list[str], Field(description="URLs or citations.")],
        origin_agent: Annotated[str, Field(description="e.g. 'claude.ai', 'claude-code'.")],
        supersedes: Annotated[
            UUID | None, Field(description="Id of the note this one replaces, if any.")
        ] = None,
    ) -> Note:
        """Save a distilled note to the user's knowledge base."""
        return store.save(title, body, tags, sources, origin_agent, supersedes)

    @mcp.tool
    def search_notes(
        query: Annotated[str, Field(description="What to look for, in natural language.")],
        tags: Annotated[
            list[str] | None, Field(description="Only notes with at least one of these tags.")
        ] = None,
        include_superseded: Annotated[
            bool, Field(description="Also return notes replaced by newer ones.")
        ] = False,
        limit: Annotated[int, Field(ge=1, le=50, description="Maximum results.")] = 8,
    ) -> SearchResults:
        """Search the user's knowledge base."""
        return SearchResults(results=store.search(query, tags, include_superseded, limit))

    return mcp
