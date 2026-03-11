from __future__ import annotations

from typing import Annotated, Any

from mcp.types import CallToolResult

from wisp_hand.batch.models import BatchRunResultModel, WaitResultModel
from wisp_hand.capabilities.models import CapabilityResultModel
from wisp_hand.capture.models import CaptureDiffResultModel, CaptureResultModel
from wisp_hand.desktop.models import (
    ActiveWindowResultModel,
    CursorPositionResultModel,
    MonitorsResultModel,
    TopologyResultModel,
    WindowsListResultModel,
)
from wisp_hand.input.models import InputDispatchResultModel
from wisp_hand.session.models import ScopeType, SessionCloseResultModel, SessionOpenResultModel
from wisp_hand.vision.models import VisionDescribeResultModel, VisionLocateResultModel


def register_tools(server) -> None:
    @server.mcp.tool(
        name="wisp_hand.capabilities",
        description="Report environment capabilities and missing dependencies.",
        structured_output=True,
    )
    def capabilities() -> Annotated[CallToolResult, dict[str, Any]]:
        return server._call(server.runtime.capabilities, CapabilityResultModel)

    @server.mcp.tool(
        name="wisp_hand.session.open",
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
        return server._call(
            server.runtime.open_session,
            SessionOpenResultModel,
            scope_type=scope_type,
            scope_target=scope_target,
            armed=armed,
            dry_run=dry_run,
            ttl_seconds=ttl_seconds,
        )

    @server.mcp.tool(
        name="wisp_hand.session.close",
        description="Close an existing session.",
        structured_output=True,
    )
    def session_close(session_id: str) -> Annotated[CallToolResult, dict[str, Any]]:
        return server._call(server.runtime.close_session, SessionCloseResultModel, session_id=session_id)

    @server.mcp.tool(
        name="wisp_hand.desktop.get_topology",
        description="Return a Hyprland topology snapshot (detail=summary|full|raw).",
        structured_output=True,
    )
    def desktop_get_topology(detail: str = "summary") -> Annotated[CallToolResult, dict[str, Any]]:
        return server._call(server.runtime.get_topology, TopologyResultModel, exclude_none=True, detail=detail)

    @server.mcp.tool(
        name="wisp_hand.desktop.get_active_window",
        description="Return the active window selector + geometry fields.",
        structured_output=True,
    )
    def desktop_get_active_window() -> Annotated[CallToolResult, dict[str, Any]]:
        return server._call(server.runtime.get_active_window, ActiveWindowResultModel, exclude_none=True)

    @server.mcp.tool(
        name="wisp_hand.desktop.get_monitors",
        description="Return minimal monitors geometry + pixel ratio mapping context.",
        structured_output=True,
    )
    def desktop_get_monitors() -> Annotated[CallToolResult, dict[str, Any]]:
        return server._call(server.runtime.get_monitors, MonitorsResultModel, exclude_none=True)

    @server.mcp.tool(
        name="wisp_hand.desktop.list_windows",
        description="List windows with minimal selector + geometry fields (limit applies).",
        structured_output=True,
    )
    def desktop_list_windows(limit: int = 50) -> Annotated[CallToolResult, dict[str, Any]]:
        return server._call(server.runtime.list_windows, WindowsListResultModel, exclude_none=True, limit=limit)

    @server.mcp.tool(
        name="wisp_hand.cursor.get_position",
        description="Return the cursor position in desktop and scope-relative coordinates.",
        structured_output=True,
    )
    def cursor_get_position(session_id: str) -> Annotated[CallToolResult, dict[str, Any]]:
        return server._call(server.runtime.get_cursor_position, CursorPositionResultModel, session_id=session_id)

    @server.mcp.tool(
        name="wisp_hand.capture.screen",
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
        return server._call(
            server.runtime.capture_screen,
            CaptureResultModel,
            exclude_none=True,
            session_id=session_id,
            target=target,
            inline=inline,
            with_cursor=with_cursor,
            downscale=downscale,
        )

    @server.mcp.tool(
        name="wisp_hand.wait",
        description="Wait for a fixed duration within a session context.",
        structured_output=True,
    )
    def wait(session_id: str, duration_ms: int) -> Annotated[CallToolResult, dict[str, Any]]:
        return server._call(server.runtime.wait, WaitResultModel, session_id=session_id, duration_ms=duration_ms)

    @server.mcp.tool(
        name="wisp_hand.capture.diff",
        description="Compare two captures and return a deterministic pixel diff summary.",
        structured_output=True,
    )
    def capture_diff(left_capture_id: str, right_capture_id: str) -> Annotated[CallToolResult, dict[str, Any]]:
        return server._call(
            server.runtime.capture_diff,
            CaptureDiffResultModel,
            left_capture_id=left_capture_id,
            right_capture_id=right_capture_id,
        )

    @server.mcp.tool(
        name="wisp_hand.batch.run",
        description="Run a sequence of supported actions inside one session.",
        structured_output=True,
    )
    def batch_run(
        session_id: str,
        steps: list[dict[str, Any]],
        stop_on_error: bool = True,
        return_mode: str = "summary",
    ) -> Annotated[CallToolResult, dict[str, Any]]:
        return server._call(
            server.runtime.batch_run,
            BatchRunResultModel,
            exclude_none=True,
            session_id=session_id,
            steps=steps,
            stop_on_error=stop_on_error,
            return_mode=return_mode,
        )

    @server.mcp.tool(
        name="wisp_hand.vision.describe",
        description="Describe an image from a capture artifact or inline image using Ollama vision.",
        structured_output=True,
    )
    def vision_describe(
        capture_id: str | None = None,
        inline_image: str | None = None,
        prompt: str | None = None,
    ) -> Annotated[CallToolResult, dict[str, Any]]:
        return server._call(
            server.runtime.vision_describe,
            VisionDescribeResultModel,
            capture_id=capture_id,
            inline_image=inline_image,
            prompt=prompt,
        )

    @server.mcp.tool(
        name="wisp_hand.vision.locate",
        description="Locate target regions within a captured image using Ollama vision.",
        structured_output=True,
    )
    def vision_locate(
        capture_id: str,
        target: str,
        limit: int = 3,
        space: str = "scope",
    ) -> Annotated[CallToolResult, dict[str, Any]]:
        return server._call(
            server.runtime.vision_locate,
            VisionLocateResultModel,
            exclude_none=True,
            capture_id=capture_id,
            target=target,
            limit=limit,
            space=space,
        )

    @server.mcp.tool(
        name="wisp_hand.pointer.move",
        description="Move the pointer to scope-relative coordinates inside an armed session.",
        structured_output=True,
    )
    def pointer_move(session_id: str, x: int, y: int) -> Annotated[CallToolResult, dict[str, Any]]:
        return server._call(server.runtime.pointer_move, InputDispatchResultModel, session_id=session_id, x=x, y=y)

    @server.mcp.tool(
        name="wisp_hand.pointer.click",
        description="Click a pointer button at scope-relative coordinates inside an armed session.",
        structured_output=True,
    )
    def pointer_click(
        session_id: str,
        x: int,
        y: int,
        button: str = "left",
    ) -> Annotated[CallToolResult, dict[str, Any]]:
        return server._call(
            server.runtime.pointer_click,
            InputDispatchResultModel,
            session_id=session_id,
            x=x,
            y=y,
            button=button,
        )

    @server.mcp.tool(
        name="wisp_hand.pointer.drag",
        description="Drag a pointer button between two scope-relative coordinates inside an armed session.",
        structured_output=True,
    )
    def pointer_drag(
        session_id: str,
        start_x: int,
        start_y: int,
        end_x: int,
        end_y: int,
        button: str = "left",
    ) -> Annotated[CallToolResult, dict[str, Any]]:
        return server._call(
            server.runtime.pointer_drag,
            InputDispatchResultModel,
            session_id=session_id,
            start_x=start_x,
            start_y=start_y,
            end_x=end_x,
            end_y=end_y,
            button=button,
        )

    @server.mcp.tool(
        name="wisp_hand.pointer.scroll",
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
        return server._call(
            server.runtime.pointer_scroll,
            InputDispatchResultModel,
            session_id=session_id,
            x=x,
            y=y,
            delta_x=delta_x,
            delta_y=delta_y,
        )

    @server.mcp.tool(
        name="wisp_hand.keyboard.type",
        description="Type text inside an armed session using the shared input safety pipeline.",
        structured_output=True,
    )
    def keyboard_type(session_id: str, text: str) -> Annotated[CallToolResult, dict[str, Any]]:
        return server._call(server.runtime.keyboard_type, InputDispatchResultModel, session_id=session_id, text=text)

    @server.mcp.tool(
        name="wisp_hand.keyboard.press",
        description="Press a key or key chord inside an armed session using the shared input safety pipeline.",
        structured_output=True,
    )
    def keyboard_press(session_id: str, keys: list[str]) -> Annotated[CallToolResult, dict[str, Any]]:
        return server._call(server.runtime.keyboard_press, InputDispatchResultModel, session_id=session_id, keys=keys)
