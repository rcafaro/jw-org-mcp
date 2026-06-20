"""MCP server implementation for JW.Org."""

import logging
from typing import Any

from mcp.server import Server
from mcp.types import TextContent, Tool

from .client import JWOrgClient
from .config import settings
from .exceptions import JWOrgMCPError
from .models import PublicationIndex

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.log_level),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

logger = logging.getLogger(__name__)

# Create MCP server
app = Server("jw-org-mcp")

# Create client instance
client = JWOrgClient()


@app.list_tools()  # type: ignore[misc, no-untyped-call]
async def list_tools() -> list[Tool]:
    """List available MCP tools."""
    return [
        Tool(
            name="search_content",
            description=(
                "Search JW.Org content including articles, videos, publications, "
                "audio, and scriptures. Extracts meaningful search terms from natural "
                "language queries."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": (
                            "The search query. Can be natural language like "
                            "'What does the Bible say about love?' The tool will "
                            "extract 'love' as the search term."
                        ),
                    },
                    "filter": {
                        "type": "string",
                        "description": "Content type filter",
                        "enum": ["all", "publications", "videos", "audio", "bible", "indexes"],
                        "default": "all",
                    },
                    "language": {
                        "type": "string",
                        "description": "Language code (E=English, S=Spanish, T=Portuguese, etc)",
                        "default": settings.default_language,
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of results to return",
                        "default": 10,
                        "minimum": 1,
                        "maximum": 50,
                    },
                },
                "required": ["query"],
            },
        ),
        Tool(
            name="get_jw_captions",
            description=(
                "Fetch video captions and metadata by video ID or any JW.org URL. "
                "Returns the video title, thumbnail URL, and subtitles."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "video_id": {
                        "type": "string",
                        "description": "Video ID or JW.Org URL",
                    },
                    "language": {
                        "type": "string",
                        "description": "Language code (E=English, P=Portuguese, S=Spanish, etc)",
                        "default": settings.default_language,
                    },
                },
                "required": ["video_id"],
            },
        ),
        Tool(
            name="get_article",
            description=(
                "Retrieve full article content from a JW.Org URL. "
                "Returns the article text with paragraphs and scripture references."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "The article URL from wol.jw.org",
                    },
                },
                "required": ["url"],
            },
        ),
        Tool(
            name="get_wol_reference",
            description=(
                "Retrieve specific paragraphs from a publication reference "
                "(e.g., 'w13 15/10 p. 27', 'cf p. 134'). "
                "Supports exact paragraph numbers or positional counting."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Publication reference (e.g., 'w13 15/10 p. 27')",
                    },
                    "start": {
                        "type": "integer",
                        "description": "Starting paragraph number (optional)",
                    },
                    "end": {
                        "type": "integer",
                        "description": "Ending paragraph number (optional)",
                    },
                    "language": {
                        "type": "string",
                        "description": "Language code (E=English, T=Portuguese, S=Spanish)",
                        "default": settings.default_language,
                    },
                },
                "required": ["query"],
            },
        ),
        Tool(
            name="get_scripture",
            description=(
                "Get scripture text by reference (e.g., 'John 3:16', '1 Thessalonians 5:3'). "
                "Returns the scripture text and reference."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "reference": {
                        "type": "string",
                        "description": "Scripture reference (e.g., 'John 3:16')",
                    },
                    "translation": {
                        "type": "string",
                        "description": "Bible translation code",
                        "default": "nwtsty",
                    },
                    "language": {
                        "type": "string",
                        "description": "Language code (E=English, P=Portuguese, S=Spanish, etc)",
                        "default": settings.default_language,
                    },
                },
                "required": ["reference"],
            },
        ),
    ]


@app.call_tool()  # type: ignore[misc]
async def call_tool(name: str, arguments: Any) -> list[TextContent]:
    """Handle tool calls."""
    try:
        if name == "search_content":
            return await _handle_search(arguments)
        elif name == "get_wol_reference":
            return await _handle_get_wol_reference(arguments)
        elif name == "get_article":
            return await _handle_get_article(arguments)
        elif name == "get_scripture":
            return await _handle_get_scripture(arguments)
        elif name == "get_jw_captions":
            return await _handle_get_jw_captions(arguments)
        else:
            return [
                TextContent(
                    type="text",
                    text=f"Unknown tool: {name}",
                )
            ]
    except JWOrgMCPError as e:
        logger.error(f"Tool error: {e}")
        return [
            TextContent(
                type="text",
                text=f"Error: {str(e)}",
            )
        ]
    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
        return [
            TextContent(
                type="text",
                text=f"Unexpected error: {str(e)}",
            )
        ]


async def _handle_search(arguments: dict[str, Any]) -> list[TextContent]:
    """Handle search_content tool call."""
    query = arguments.get("query", "")
    filter_type = arguments.get("filter", "all")
    language = arguments.get("language")
    limit = arguments.get("limit", 10)

    logger.info(
        f"Searching: query={query}, filter={filter_type}, "
        f"language={language or settings.default_language}"
    )

    response, metadata = await client.search(
        query=query,
        filter_type=filter_type,
        language=language,
        limit=limit,
    )

    # Format results
    result_text = f"# Search Results for '{response.query}'\n\n"
    result_text += f"**Total Results:** {response.total}\n"
    result_text += f"**Filter:** {response.filter}\n"
    result_text += f"**Source:** {metadata.source_url}\n"
    result_text += f"**Timestamp:** {metadata.timestamp.isoformat()}\n\n"

    if not response.results:
        result_text += "No results found.\n"
    else:
        result_text += f"## Results (showing {len(response.results)} of {response.total})\n\n"
        for i, result in enumerate(response.results, 1):
            result_text += f"### {i}. {result.title}\n\n"
            if result.context:
                result_text += f"**Source:** {result.context}\n\n"
            result_text += f"{result.snippet}\n\n"
            result_text += f"**URL:** {result.url}\n\n"
            result_text += "---\n\n"

    return [TextContent(type="text", text=result_text)]


async def _handle_get_wol_reference(arguments: dict[str, Any]) -> list[TextContent]:
    """Handle get_wol_reference tool call."""
    query = arguments.get("query", "")
    start = arguments.get("start")
    end = arguments.get("end")
    language = arguments.get("language")

    logger.info(
        f"Fetching WOL reference: query={query}, start={start}, end={end}, "
        f"language={language or settings.default_language}"
    )

    content, metadata = await client.get_wol_reference(
        query=query,
        start_paragraph=start,
        end_paragraph=end,
        language=language,
    )

    # Format response
    result_text = f"# Reference: {content.query}\n\n"
    result_text += f"**Source:** {metadata.source_url}\n"
    result_text += f"**Timestamp:** {metadata.timestamp.isoformat()}\n"
    if content.pages:
        result_text += f"**Pages:** {content.pages[0]}–{content.pages[-1]}\n"
    result_text += f"**Total paragraphs in article:** {content.total_paragraphs_in_article}\n\n"

    result_text += "---\n\n"

    if not content.paragraphs:
        result_text += "No paragraphs found for the specified range.\n"
    else:
        for p in content.paragraphs:
            if p.is_header:
                result_text += f"## {p.text}\n\n"
            else:
                label = f"§{p.number}" if p.number else "§[pos]"
                result_text += f"**{label}:** {p.text}\n\n"

    return [TextContent(type="text", text=result_text)]


async def _handle_get_article(arguments: dict[str, Any]) -> list[TextContent]:
    """Handle get_article tool call."""
    url = arguments.get("url", "")

    logger.info(f"Fetching article: {url}")

    content, metadata = await client.get_article(url)

    if isinstance(content, PublicationIndex):
        # Format publication index/table of contents
        result_text = f"# {content.title}\n\n"
        result_text += (
            "**Note:** This URL points to a publication index, not a specific "
            "article. Use one of the article URLs below with get_article to "
            "retrieve the full content.\n\n"
        )
        result_text += f"**Source:** {metadata.source_url}\n"
        result_text += f"**Timestamp:** {metadata.timestamp.isoformat()}\n\n"
        result_text += "## Available Articles\n\n"
        for i, entry in enumerate(content.articles, 1):
            result_text += f"{i}. **{entry.title}**\n"
            result_text += f"   URL: {entry.url}\n\n"
    else:
        # Format article
        result_text = f"# {content.title}\n\n"
        result_text += f"**Source:** {metadata.source_url}\n"
        result_text += f"**Timestamp:** {metadata.timestamp.isoformat()}\n\n"

        result_text += "## Content\n\n"
        for para in content.paragraphs:
            result_text += f"{para}\n\n"

        if content.references:
            result_text += "## Scripture References\n\n"
            for ref in content.references:
                result_text += f"- {ref}\n"

    return [TextContent(type="text", text=result_text)]


async def _handle_get_scripture(arguments: dict[str, Any]) -> list[TextContent]:
    """Handle get_scripture tool call."""
    reference = arguments.get("reference", "")
    translation = arguments.get("translation", "nwtsty")
    language = arguments.get("language")

    logger.info(f"Fetching scripture: {reference} (lang={language or settings.default_language})")

    scripture, metadata = await client.get_scripture(reference, translation, language)

    # Format scripture
    result_text = f"# {scripture['reference']}\n\n"
    result_text += f"{scripture['text']}\n\n"
    result_text += f"**Source:** {metadata.source_url}\n"
    result_text += f"**Timestamp:** {metadata.timestamp.isoformat()}\n"

    return [TextContent(type="text", text=result_text)]


async def _handle_get_jw_captions(arguments: dict[str, Any]) -> list[TextContent]:
    """Handle get_jw_captions tool call."""
    video_id = arguments.get("video_id", "")
    language = arguments.get("language")

    logger.info(f"Fetching video captions: {video_id} (lang={language or settings.default_language})")

    captions, metadata = await client.get_video_captions(video_id, language)

    # Format captions response
    result_text = f"# {captions.title}\n\n"
    if captions.thumbnail:
        result_text += f"![Thumbnail]({captions.thumbnail})\n\n"
    result_text += f"**Source:** {metadata.source_url}\n"
    result_text += f"**Timestamp:** {metadata.timestamp.isoformat()}\n\n"
    result_text += "## Subtitles\n\n"
    result_text += f"{captions.subtitles}\n"

    return [TextContent(type="text", text=result_text)]




async def cleanup() -> None:
    """Cleanup resources on shutdown."""
    logger.info("Shutting down JW.Org MCP server")
    await client.close()
