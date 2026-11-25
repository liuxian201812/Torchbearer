"""Serve a host-scoped read-only corpus using the official MCP Python v1 SDK."""

import argparse
import json
from typing import Annotated

from .knowledge import ReadOnlyKnowledge


def create_server(corpus_path: str, scope_path: str):
    from mcp.server.fastmcp import FastMCP
    from pydantic import Field

    with open(scope_path, encoding="utf-8") as f:
        scope = json.load(f)
    knowledge = ReadOnlyKnowledge(corpus_path, scope["allowed_record_ids"])
    server = FastMCP("Torchbearer Knowledge")

    @server.tool()
    def search_records(query: str, limit: Annotated[int, Field(strict=True, ge=1, le=50)] = 10) -> list[dict]:
        """Search records visible in the host-assigned scientific context."""
        return knowledge.search(query, limit)

    @server.tool()
    def read_record(record_id: str) -> dict:
        """Read one allowed claim, source card or scientific brief by stable ID."""
        return knowledge.read(record_id)

    return server


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", required=True)
    parser.add_argument("--scope", required=True)
    args = parser.parse_args()
    try:
        server = create_server(args.corpus, args.scope)
    except ModuleNotFoundError as exc:
        if exc.name == "mcp" or (exc.name and exc.name.startswith("mcp.")):
            parser.error("Install the optional MCP dependency: pip install 'mcp>=1.12,<2'")
        raise
    server.run(transport="stdio")


if __name__ == "__main__":
    main()
