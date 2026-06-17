# syntax=docker/dockerfile:1
FROM python:3.13-slim AS base

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

# Set working directory
WORKDIR /app

# Copy project files (README.md needed for hatchling metadata)
COPY pyproject.toml uv.lock ./
COPY src/ ./src/
COPY README.md ./

# Install dependencies and the project (non-interactive, frozen from lock file)
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

# Create non-root user
RUN useradd --create-home jworg

# Give the non-root user access to the venv
RUN chown -R jworg:jworg /app

# Switch to non-root user
USER jworg

# Default configuration (override via env_file or -e flags)
ENV JWORG_MCP_CACHE_TTL_SECONDS=900 \
    JWORG_MCP_ENABLE_CACHE=true \
    JWORG_MCP_REQUEST_TIMEOUT=30 \
    JWORG_MCP_MAX_RETRIES=3 \
    JWORG_MCP_DEFAULT_LANGUAGE=T \
    JWORG_MCP_DEFAULT_SEARCH_LIMIT=10 \
    JWORG_MCP_LOG_LEVEL=INFO

# Run the MCP server (stdio mode) - use venv python directly to avoid uv run overhead
ENTRYPOINT ["/app/.venv/bin/jw-org-mcp"]
