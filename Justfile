set shell := ["bash", "-eu", "-o", "pipefail", "-c"]

# Default runtime config used by `just ...` commands.
#
# Override on demand:
#   just inspector config=~/.config/wisp-hand/config.toml
config ?= "docs/example_config.toml"

# Run a preflight check and pretty-print the JSON report (requires `jq`).
doctor:
  uv run wisp-hand-mcp --config {{config}} doctor --json | jq .

# Start the MCP server (uses transport from config; override via `transport=...`).
transport ?= ""
serve:
  if [[ -n "{{transport}}" ]]; then \
    uv run wisp-hand-mcp --config {{config}} --transport "{{transport}}"; \
  else \
    uv run wisp-hand-mcp --config {{config}}; \
  fi

# Start MCP Inspector (UI) and spawn the server via stdio.
#
# Notes:
# - `--` is required so inspector won't consume the server's `--config` flag.
# - Inspector UI will be served at http://localhost:6274 by default.
inspector:
  npx --yes @modelcontextprotocol/inspector -- uv run wisp-hand-mcp --config {{config}} --transport stdio

# Same as `inspector`, but disables automatic browser opening.
inspector-no-open:
  MCP_AUTO_OPEN_ENABLED=false npx --yes @modelcontextprotocol/inspector -- uv run wisp-hand-mcp --config {{config}} --transport stdio

