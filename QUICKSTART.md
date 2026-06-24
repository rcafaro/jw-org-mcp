# Quick Start Guide

## Installation

```bash
# Install dependencies
uv sync

# Install with dev dependencies for testing
uv sync --group dev
```

## Running the MCP Server

```bash
uv run jw-org-mcp
```

The server will start and wait for MCP protocol messages via stdin/stdout.

## Testing the Implementation

```bash
# Run all tests
uv run pytest

# Run with verbose output
uv run pytest -v

# Run with coverage report
uv run pytest --cov=jw_org_mcp --cov-report=html

# Run specific test file
uv run pytest tests/test_parser.py
```

## Code Quality

```bash
# Check code with linter
uv run ruff check .

# Format code
uv run ruff format .

# Type checking (requires stubs installation)
uv run mypy src/jw_org_mcp
```

## Configuration

Set environment variables with the `JWORG_MCP_` prefix:

```bash
# Request timeout
export JWORG_MCP_REQUEST_TIMEOUT=30

# Logging
export JWORG_MCP_LOG_LEVEL=INFO
```

## Testing with MCP Inspector

You can test the MCP server using the MCP Inspector tool:

```bash
# Install MCP Inspector (if not already installed)
npm install -g @modelcontextprotocol/inspector

# Run the server through the inspector
npx @modelcontextprotocol/inspector uv run jw-org-mcp
```

## Example Usage

Once connected via MCP, you can use these tools:

### get_wol_reference

Retrieve specific paragraphs from a publication reference (e.g., 'w13 15/10 p. 27', 'cf p. 134'). 
Supports precise paragraph extraction using exact numbering or positional counting. 

It handles complex queries including page ranges (pp. 1041-1043), paragraph ranges (§§ 4-6), and multiple semicolon-separated references. For reference books (like the 'it' book), it can aggregate multiple entries appearing on the same page range.

**Parameters:**
- `query` (required): Publication reference (e.g., 'w13 15/10 p. 27', 'it-2 pp. 1041-1043')
- `start` (optional): Starting paragraph number (default: 1)
- `end` (optional): Ending paragraph number
- `language` (optional): Language code - `E` for English, `T` for Portuguese, `S` for Spanish (default: `E`)

**Example:**
```json
{
  "query": "it-2 pp. 1041-1043",
  "language": "E"
}
```


### Search Content
Search natural language expressions (not publication references)

```json
{
  "name": "search_content",
  "arguments": {
    "query": "What does the Bible say about love?",
    "filter": "all",
    "limit": 5
  }
}
```

### Get Article

```json
{
  "name": "get_article",
  "arguments": {
    "url": "https://wol.jw.org/en/wol/d/r1/lp-e/1985720"
  }
}
```

### Get Scripture

```json
{
  "name": "get_scripture",
  "arguments": {
    "reference": "John 3:16"
  }
}
```

## Project Structure

```
jw-org-mcp/
├── src/jw_org_mcp/
│   ├── __init__.py       # Entry point & main
│   ├── auth.py           # Authentication & CDN discovery
│   ├── client.py         # JW.Org API client
│   ├── config.py         # Configuration
│   ├── exceptions.py     # Custom exceptions
│   ├── models.py         # Pydantic models
│   ├── parser.py         # Content parsers
│   └── server.py         # MCP server
├── tests/                # Test suite
├── docs/                 # Documentation
└── pyproject.toml       # Project config
```

## Development Workflow

1. Make changes to the code
2. Run tests: `uv run pytest`
3. Check linting: `uv run ruff check .`
4. Format code: `uv run ruff format .`
5. Verify coverage: `uv run pytest --cov-report=html`
6. Open `htmlcov/index.html` to view coverage report

## Troubleshooting

### Tests Failing

- Ensure all dependencies are installed: `uv sync --group dev`
- Check Python version: `python --version` (should be 3.13+)

### Import Errors

- Make sure the package is installed in editable mode
- Run `uv sync` to reinstall

### Authentication Issues

- The tool automatically discovers the CDN and gets tokens
- Check logs for authentication errors
- Verify network connectivity to jw.org

## Next Steps

- Read the full [README.md](README.md)
- Review the [PRD](docs/jw-org-mcp-prd.md)
- Check the [CLAUDE.md](CLAUDE.md) for architecture details
