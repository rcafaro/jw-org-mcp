"""JW.Org MCP Tool - Model Context Protocol server for verified jw.org content access."""

import asyncio

import anyio
from mcp.server.stdio import stdio_server

from .server import app, cleanup


def main() -> None:
    """Main entry point for the MCP server."""
    asyncio.run(async_main())


async def async_main() -> None:
    """Async main function."""
    try:
        async with stdio_server() as (read_stream, write_stream):
            try:
                await app.run(
                    read_stream,
                    write_stream,
                    app.create_initialization_options(),
                )
            except* anyio.ClosedResourceError:
                # Ignore closed resource errors during shutdown
                pass
    finally:
        await cleanup()
