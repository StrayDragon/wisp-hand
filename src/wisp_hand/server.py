from __future__ import annotations

import json
from typing import Annotated, Any, cast

from mcp.server.fastmcp import FastMCP
from mcp.types import CallToolResult, TextContent

from wisp_hand.config import load_runtime_config
from wisp_hand.errors import WispHandError, internal_error
from wisp_hand.models import (
    CapabilityResultModel,
    CaptureResultModel,
    CursorPositionResultModel,
    ScopeType,
    SessionCloseResultModel,
    SessionOpenResultModel,
    TopologyResultModel,
)
from wisp_hand.runtime import WispHandRuntime


class WispHandServer:
    def __init__(self, runtime: WispHandRuntime) -> None:
        self.runtime = runtime
        self.mcp = FastMCP(
            name="Wisp Hand",
            instructions="Hyprland-first computer-use MCP runtime foundation.",
            log_level=runtime.config.server.log_level,
            host=runtime.config.server.host,
            port=runtime.config.server.port,
        )
        self._register_tools()

    def _register_tools(self) -> None:
        @self.mcp.tool(
            name="hand.capabilities",
            description="Report environment capabilities and missing dependencies.",
            structured_output=True,
        )
        def capabilities() -> Annotated[CallToolResult, dict[str, Any]]:
            return self._call(self.runtime.capabilities, CapabilityResultModel)

        @self.mcp.tool(
            name="hand.session.open",
            description="Create a scoped session for future tool calls.",
            structured_output=True,
        )
        def session_open(
            scope_type: ScopeType,
            scope_target: dict[str, Any] | str | int | float | bool | None = None,
            armed: bool | None = None,
            dry_run: bool | None = None,
            ttl_seconds: int | None = None,
        ) -> Annotated[CallToolResult, dict[str, Any]]:
            return self._call(
                self.runtime.open_session,
                SessionOpenResultModel,
                scope_type=scope_type,
                scope_target=scope_target,
                armed=armed,
                dry_run=dry_run,
                ttl_seconds=ttl_seconds,
            )

        @self.mcp.tool(
            name="hand.session.close",
            description="Close an existing session.",
            structured_output=True,
        )
        def session_close(session_id: str) -> Annotated[CallToolResult, dict[str, Any]]:
            return self._call(self.runtime.close_session, SessionCloseResultModel, session_id=session_id)

        @self.mcp.tool(
            name="hand.desktop.get_topology",
            description="Return Hyprland monitors, workspaces, active window and window list.",
            structured_output=True,
        )
        def desktop_get_topology() -> Annotated[CallToolResult, dict[str, Any]]:
            return self._call(self.runtime.get_topology, TopologyResultModel)

        @self.mcp.tool(
            name="hand.cursor.get_position",
            description="Return the cursor position in desktop and scope-relative coordinates.",
            structured_output=True,
        )
        def cursor_get_position(session_id: str) -> Annotated[CallToolResult, dict[str, Any]]:
            return self._call(self.runtime.get_cursor_position, CursorPositionResultModel, session_id=session_id)

        @self.mcp.tool(
            name="hand.capture.screen",
            description="Capture the current desktop or session-compatible target into the artifact store.",
            structured_output=True,
        )
        def capture_screen(
            session_id: str,
            target: str = "scope",
            inline: bool = False,
            with_cursor: bool = False,
            downscale: float | None = None,
        ) -> Annotated[CallToolResult, dict[str, Any]]:
            return self._call(
                self.runtime.capture_screen,
                CaptureResultModel,
                session_id=session_id,
                target=target,
                inline=inline,
                with_cursor=with_cursor,
                downscale=downscale,
            )

    @staticmethod
    def _call(callback, response_model, /, **kwargs) -> CallToolResult:
        try:
            payload = response_model.model_validate(callback(**kwargs)).model_dump(mode="json")
            return WispHandServer._result(payload)
        except WispHandError as exc:
            return WispHandServer._result(exc.to_payload(), is_error=True)
        except Exception as exc:  # pragma: no cover - defensive wrapper
            return WispHandServer._result(internal_error(str(exc)).to_payload(), is_error=True)

    @staticmethod
    def _result(payload: dict[str, Any], *, is_error: bool = False) -> CallToolResult:
        return CallToolResult(
            content=[
                TextContent(
                    type="text",
                    text=json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True),
                )
            ],
            structuredContent=payload,
            isError=is_error,
        )

    def run(self, *, transport: str | None = None) -> None:
        self.mcp.run(transport=cast(str, transport or self.runtime.config.server.transport))


def create_server(runtime: WispHandRuntime | None = None) -> WispHandServer:
    return WispHandServer(runtime or WispHandRuntime(config=load_runtime_config()))
