from __future__ import annotations

import json
from typing import Annotated, Any, cast

from mcp.server.fastmcp import FastMCP
from mcp.types import CallToolResult, TextContent

from wisp_hand.config import load_runtime_config
from wisp_hand.errors import WispHandError, internal_error
from wisp_hand.models import (
    BatchRunResultModel,
    CapabilityResultModel,
    CaptureResultModel,
    CaptureDiffResultModel,
    CursorPositionResultModel,
    InputDispatchResultModel,
    PointerButton,
    ScopeType,
    SessionCloseResultModel,
    SessionOpenResultModel,
    TopologyResultModel,
    VisionDescribeResultModel,
    VisionLocateResultModel,
    WaitResultModel,
)
from wisp_hand.runtime import WispHandRuntime


class WispHandServer:
    def __init__(self, runtime: WispHandRuntime) -> None:
        self.runtime = runtime
        self.mcp = FastMCP(
            name="Wisp Hand",
            instructions="Hyprland-first computer-use MCP runtime foundation.",
            log_level=runtime.config.logging.level,
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

        @self.mcp.tool(
            name="hand.wait",
            description="Wait for a fixed duration within a session context.",
            structured_output=True,
        )
        def wait(session_id: str, duration_ms: int) -> Annotated[CallToolResult, dict[str, Any]]:
            return self._call(
                self.runtime.wait,
                WaitResultModel,
                session_id=session_id,
                duration_ms=duration_ms,
            )

        @self.mcp.tool(
            name="hand.capture.diff",
            description="Compare two captures and return a deterministic pixel diff summary.",
            structured_output=True,
        )
        def capture_diff(
            left_capture_id: str,
            right_capture_id: str,
        ) -> Annotated[CallToolResult, dict[str, Any]]:
            return self._call(
                self.runtime.capture_diff,
                CaptureDiffResultModel,
                left_capture_id=left_capture_id,
                right_capture_id=right_capture_id,
            )

        @self.mcp.tool(
            name="hand.batch.run",
            description="Run a sequence of supported actions inside one session.",
            structured_output=True,
        )
        def batch_run(
            session_id: str,
            steps: list[dict[str, Any]],
            stop_on_error: bool = True,
        ) -> Annotated[CallToolResult, dict[str, Any]]:
            return self._call(
                self.runtime.batch_run,
                BatchRunResultModel,
                session_id=session_id,
                steps=steps,
                stop_on_error=stop_on_error,
            )

        @self.mcp.tool(
            name="hand.vision.describe",
            description="Describe an image from a capture artifact or inline image using Ollama vision.",
            structured_output=True,
        )
        def vision_describe(
            capture_id: str | None = None,
            inline_image: str | None = None,
            prompt: str | None = None,
        ) -> Annotated[CallToolResult, dict[str, Any]]:
            return self._call(
                self.runtime.vision_describe,
                VisionDescribeResultModel,
                capture_id=capture_id,
                inline_image=inline_image,
                prompt=prompt,
            )

        @self.mcp.tool(
            name="hand.vision.locate",
            description="Locate target regions within a captured image using Ollama vision.",
            structured_output=True,
        )
        def vision_locate(
            capture_id: str,
            target: str,
        ) -> Annotated[CallToolResult, dict[str, Any]]:
            return self._call(
                self.runtime.vision_locate,
                VisionLocateResultModel,
                capture_id=capture_id,
                target=target,
            )

        @self.mcp.tool(
            name="hand.pointer.move",
            description="Move the pointer to scope-relative coordinates inside an armed session.",
            structured_output=True,
        )
        def pointer_move(session_id: str, x: int, y: int) -> Annotated[CallToolResult, dict[str, Any]]:
            return self._call(
                self.runtime.pointer_move,
                InputDispatchResultModel,
                session_id=session_id,
                x=x,
                y=y,
            )

        @self.mcp.tool(
            name="hand.pointer.click",
            description="Click a pointer button at scope-relative coordinates inside an armed session.",
            structured_output=True,
        )
        def pointer_click(
            session_id: str,
            x: int,
            y: int,
            button: PointerButton = "left",
        ) -> Annotated[CallToolResult, dict[str, Any]]:
            return self._call(
                self.runtime.pointer_click,
                InputDispatchResultModel,
                session_id=session_id,
                x=x,
                y=y,
                button=button,
            )

        @self.mcp.tool(
            name="hand.pointer.drag",
            description="Drag a pointer button between two scope-relative coordinates inside an armed session.",
            structured_output=True,
        )
        def pointer_drag(
            session_id: str,
            start_x: int,
            start_y: int,
            end_x: int,
            end_y: int,
            button: PointerButton = "left",
        ) -> Annotated[CallToolResult, dict[str, Any]]:
            return self._call(
                self.runtime.pointer_drag,
                InputDispatchResultModel,
                session_id=session_id,
                start_x=start_x,
                start_y=start_y,
                end_x=end_x,
                end_y=end_y,
                button=button,
            )

        @self.mcp.tool(
            name="hand.pointer.scroll",
            description="Scroll at scope-relative coordinates inside an armed session.",
            structured_output=True,
        )
        def pointer_scroll(
            session_id: str,
            x: int,
            y: int,
            delta_x: int = 0,
            delta_y: int = 0,
        ) -> Annotated[CallToolResult, dict[str, Any]]:
            return self._call(
                self.runtime.pointer_scroll,
                InputDispatchResultModel,
                session_id=session_id,
                x=x,
                y=y,
                delta_x=delta_x,
                delta_y=delta_y,
            )

        @self.mcp.tool(
            name="hand.keyboard.type",
            description="Type text inside an armed session using the shared input safety pipeline.",
            structured_output=True,
        )
        def keyboard_type(session_id: str, text: str) -> Annotated[CallToolResult, dict[str, Any]]:
            return self._call(
                self.runtime.keyboard_type,
                InputDispatchResultModel,
                session_id=session_id,
                text=text,
            )

        @self.mcp.tool(
            name="hand.keyboard.press",
            description="Press a key or key chord inside an armed session using the shared input safety pipeline.",
            structured_output=True,
        )
        def keyboard_press(
            session_id: str,
            keys: list[str],
        ) -> Annotated[CallToolResult, dict[str, Any]]:
            return self._call(
                self.runtime.keyboard_press,
                InputDispatchResultModel,
                session_id=session_id,
                keys=keys,
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
