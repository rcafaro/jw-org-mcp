# Docker deployment instructions

# 1. Clone repo

# 2. Build the image
docker compose build

# 3. Test it runs (exits cleanly — stdio MCP servers are ephemeral)
docker run --rm jw-org-mcp 2>&1 | head -5

# 4. Clean up build artifacts (optional)
docker compose down --rmi local --volumes

delete repo directory

# 5. configure MCP server in Hermes Agent
Add MCP Server and restart:

name: jw-org
{
  "command": "docker",
  "args": [
    "run",
    "-i",
    "--rm",
    "jw-org-mcp-jw-org-mcp"
  ],
  "timeout": 60,
  "connect_timeout": 30
}

