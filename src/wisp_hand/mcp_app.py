from __future__ import annotations

"""
FastMCP entrypoint for `mcp run/dev/install`.

Usage examples:
  uv run mcp dev src/wisp_hand/mcp_app.py:mcp --with-editable .
  uv run mcp run src/wisp_hand/mcp_app.py:mcp --transport stdio
"""

from wisp_hand.protocol.mcp_server import create_server

# NOTE: mcp CLI expects a global FastMCP object named `mcp`/`server`/`app`.
mcp = create_server().mcp

