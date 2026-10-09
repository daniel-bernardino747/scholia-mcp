"""Command line entry point: `scholia-mcp serve` and `scholia-mcp reindex`."""

import argparse
import sys

from pydantic import ValidationError

from scholia_mcp.auth import build_auth
from scholia_mcp.config import Settings
from scholia_mcp.embeddings import build_embedder
from scholia_mcp.server import create_server
from scholia_mcp.store import SchemaMismatch, open_store, reindex


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="scholia-mcp")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("serve", help="Run the MCP server over streamable HTTP at /mcp.")
    commands.add_parser(
        "reindex",
        help="Rebuild embeddings and full-text vectors with the configured embedder and"
        " FTS_LANGUAGE (after changing them). Stop the server first.",
    )
    args = parser.parse_args(argv)

    try:
        settings = Settings()  # pyright: ignore[reportCallIssue]
    except ValidationError as error:
        sys.exit(f"Invalid configuration, refusing to start:\n{error}")

    match args.command:
        case "serve":
            serve(settings)
        case "reindex":
            embedder = build_embedder(settings)
            count = reindex(settings.database_url, embedder, settings.fts_language)
            print(
                f"Reindexed {count} notes with {embedder.provider}/{embedder.model}"
                f" ({embedder.dim} dims), FTS language {settings.fts_language}."
            )


def serve(settings: Settings) -> None:
    try:
        store = open_store(
            settings.database_url,
            build_embedder(settings),
            settings.fts_language,
            settings.min_similarity,
        )
    except SchemaMismatch as error:
        sys.exit(str(error))
    with store:
        server = create_server(store, auth=build_auth(settings))
        server.run(transport="http", host=settings.host, port=settings.port, path="/mcp")
