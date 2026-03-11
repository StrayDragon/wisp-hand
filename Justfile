set shell := ["bash", "-eu", "-o", "pipefail", "-c"]

# Default runtime config used by `just ...` commands.
#
# Override on demand:
#   just inspector config=~/.config/wisp-hand/config.toml

# Run a preflight check and pretty-print the JSON report (requires `jq`).
doctor config="docs/example_config.toml":
  uv run wisp-hand doctor --config "{{config}}" --json | jq .

# Start the MCP server (uses transport from config; override via `transport=...`).
serve config="docs/example_config.toml" transport="":
  if [[ -n "{{transport}}" ]]; then \
    uv run wisp-hand mcp --config "{{config}}" --transport "{{transport}}"; \
  else \
    uv run wisp-hand mcp --config "{{config}}"; \
  fi

# Start MCP Inspector (UI) and spawn the server via stdio.
#
# Notes:
# - `--` is required so inspector won't consume the server's `--config` flag.
# - Inspector UI will be served at http://localhost:6274 by default.
inspector config="docs/example_config.toml":
  npx --yes @modelcontextprotocol/inspector -- uv run wisp-hand mcp --config "{{config}}" --transport stdio

# Same as `inspector`, but disables automatic browser opening.
inspector-no-open config="docs/example_config.toml":
  MCP_AUTO_OPEN_ENABLED=false npx --yes @modelcontextprotocol/inspector -- uv run wisp-hand mcp --config "{{config}}" --transport stdio

# Serve MkDocs site locally (docs/mkdocs).
docs-serve:
  NO_MKDOCS_2_WARNING=1 uv run mkdocs serve

# Build MkDocs site (fails on warnings).
docs-build:
  NO_MKDOCS_2_WARNING=1 uv run mkdocs build --strict
