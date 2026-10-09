"""Command line entry point: `scholia-mcp serve` and `scholia-mcp reindex`."""

import argparse
import sys
from uuid import UUID

import httpx
import psycopg
from pydantic import ValidationError

from scholia_mcp.auth import build_auth
from scholia_mcp.config import Settings
from scholia_mcp.embeddings import Embedder, build_embedder
from scholia_mcp.server import create_server
from scholia_mcp.store import NoteNotFound, SchemaMismatch, open_store, reindex, unarchive


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="scholia-mcp")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("serve", help="Run the MCP server over streamable HTTP at /mcp.")
    commands.add_parser(
        "reindex",
        help="Rebuild embeddings and full-text vectors with the configured embedder and"
        " FTS_LANGUAGE (after changing them). Stop the server first.",
    )
    unarchive_parser = commands.add_parser(
        "unarchive", help="Put an archived note back into search results."
    )
    unarchive_parser.add_argument("id", type=UUID, help="The note's id.")
    args = parser.parse_args(argv)

    try:
        settings = Settings()  # pyright: ignore[reportCallIssue]
    except ValidationError as error:
        sys.exit(f"Invalid configuration, refusing to start:\n{error}")

    if args.command == "unarchive":
        try:
            note = unarchive(settings.database_url, args.id)
        except (NoteNotFound, psycopg.Error) as error:
            sys.exit(str(error))
        print(f"Unarchived {note.title!r}; status is now {note.status}.")
        return

    try:
        embedder = build_embedder(settings)
    except ValueError as error:  # e.g. an unknown EMBEDDING_MODEL
        sys.exit(f"Invalid configuration, refusing to start:\n{error}")

    match args.command:
        case "serve":
            serve(settings, embedder)
        case "reindex":
            run_reindex(settings, embedder)


def run_reindex(settings: Settings, embedder: Embedder) -> None:
    try:
        count = reindex(settings.database_url, embedder, settings.fts_language)
    except (httpx.HTTPError, psycopg.Error, ValueError) as error:
        sys.exit(f"Reindex failed; the database was left unchanged.\n{error}")
    print(
        f"Reindexed {count} notes with {embedder.provider}/{embedder.model}"
        f" ({embedder.dim} dims), FTS language {settings.fts_language}."
    )


def serve(settings: Settings, embedder: Embedder) -> None:
    try:
        store = open_store(
            settings.database_url, embedder, settings.fts_language, settings.min_similarity
        )
    except (SchemaMismatch, ValueError) as error:
        sys.exit(str(error))
    with store:
        server = create_server(store, auth=build_auth(settings))
        server.run(transport="http", host=settings.host, port=settings.port, path="/mcp")
