# Docker deployment instructions

# 1. Clone repo

# 2. Build the image
docker compose build

# 3. Test it runs (exits cleanly — stdio MCP servers are ephemeral)
docker run --rm jw-org-mcp 2>&1 | head -5

# 4. Clean up build artifacts (optional)
docker compose down --rmi local --volumes