from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Annotated, Any, cast

import anyio
from mcp.server.fastmcp import FastMCP
from mcp.types import (
    CallToolResult,
    ContentBlock,
    CreateTaskResult,
    TASK_OPTIONAL,
    TextContent,
    Tool,
    ToolExecution,
)

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
        self._enable_task_augmented_execution()

    def _register_tools(self) -> None:
        @self.mcp.tool(
            name="wisp_hand.capabilities",
            description="Report environment capabilities and missing dependencies.",
            structured_output=True,
        )
        def capabilities() -> Annotated[CallToolResult, dict[str, Any]]:
            return self._call(self.runtime.capabilities, CapabilityResultModel)

        @self.mcp.tool(
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
            name="wisp_hand.session.close",
            description="Close an existing session.",
            structured_output=True,
        )
        def session_close(session_id: str) -> Annotated[CallToolResult, dict[str, Any]]:
            return self._call(self.runtime.close_session, SessionCloseResultModel, session_id=session_id)

        @self.mcp.tool(
            name="wisp_hand.desktop.get_topology",
            description="Return a Hyprland topology snapshot (detail=summary|full|raw).",
            structured_output=True,
        )
        def desktop_get_topology(detail: str = "summary") -> Annotated[CallToolResult, dict[str, Any]]:
            return self._call(self.runtime.get_topology, TopologyResultModel, exclude_none=True, detail=detail)

        @self.mcp.tool(
            name="wisp_hand.cursor.get_position",
            description="Return the cursor position in desktop and scope-relative coordinates.",
            structured_output=True,
        )
        def cursor_get_position(session_id: str) -> Annotated[CallToolResult, dict[str, Any]]:
            return self._call(self.runtime.get_cursor_position, CursorPositionResultModel, session_id=session_id)

        @self.mcp.tool(
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
            name="wisp_hand.wait",
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
            name="wisp_hand.capture.diff",
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
            name="wisp_hand.batch.run",
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
            name="wisp_hand.vision.describe",
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
            name="wisp_hand.vision.locate",
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
            name="wisp_hand.pointer.move",
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
            name="wisp_hand.pointer.click",
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
            name="wisp_hand.keyboard.type",
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
            name="wisp_hand.keyboard.press",
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

    def _enable_task_augmented_execution(self) -> None:
        # FastMCP doesn't expose tasks yet. We enable tasks on the underlying lowlevel server
        # and override list_tools/tools/call to provide taskSupport + task-augmented execution.
        self.mcp._mcp_server.experimental.enable_tasks()  # pyright: ignore[reportPrivateUsage]
        self.mcp._mcp_server.list_tools()(self._list_tools)  # pyright: ignore[reportPrivateUsage]
        self.mcp._mcp_server.call_tool(validate_input=False)(self._call_tool)  # pyright: ignore[reportPrivateUsage]

    async def _list_tools(self) -> list[Tool]:
        tools = self.mcp._tool_manager.list_tools()  # pyright: ignore[reportPrivateUsage]
        return [
            Tool(
                name=info.name,
                title=info.title,
                description=info.description,
                inputSchema=info.parameters,
                outputSchema=info.output_schema,
                annotations=info.annotations,
                icons=info.icons,
                _meta=info.meta,
                execution=ToolExecution(taskSupport=TASK_OPTIONAL),
            )
            for info in tools
        ]

    async def _call_tool(
        self, name: str, arguments: dict[str, Any]
    ) -> (
        Sequence[ContentBlock]
        | dict[str, Any]
        | tuple[Sequence[ContentBlock], dict[str, Any]]
        | CallToolResult
        | CreateTaskResult
    ):
        try:
            request_context = self.mcp._mcp_server.request_context  # pyright: ignore[reportPrivateUsage]
        except LookupError:  # pragma: no cover - should only happen outside request contexts
            request_context = None

        experimental = getattr(request_context, "experimental", None)
        if experimental is not None and experimental.is_task:
            return await self._call_tool_as_task(experimental, name, arguments)

        context = self.mcp.get_context()
        return await self.mcp._tool_manager.call_tool(  # pyright: ignore[reportPrivateUsage]
            name,
            arguments,
            context=context,
            convert_result=True,
        )

    @staticmethod
    def _normalize_task_result(result: Any) -> CallToolResult:
        if isinstance(result, CallToolResult):
            return result

        # FastMCP's conversion pipeline may return either a structured payload (dict)
        # or raw content blocks (unstructured). Normalize for tasks store.
        if isinstance(result, dict):
            return CallToolResult(
                content=[TextContent(type="text", text=json.dumps(result, ensure_ascii=True, indent=2, sort_keys=True))],
                structuredContent=result,
                isError=False,
            )

        if isinstance(result, tuple) and len(result) == 2:
            unstructured, structured = result
            if not isinstance(structured, dict):
                raise TypeError("Structured tool result must be a dict")
            return CallToolResult(
                content=list(unstructured),
                structuredContent=structured,
                isError=False,
            )

        if isinstance(result, Sequence):
            return CallToolResult(content=list(result), structuredContent=None, isError=False)

        raise TypeError(f"Unexpected tool return type: {type(result).__name__}")

    def _call_sync_tool_by_name(self, name: str, arguments: dict[str, Any]) -> CallToolResult:
        """
        Run a tool call synchronously (no MCP request context required).

        This is used for task execution where we run the blocking work in a thread so
        the server event loop stays responsive (polling/cancel/etc).
        """
        match name:
            case "wisp_hand.capabilities":
                return self._call(self.runtime.capabilities, CapabilityResultModel)
            case "wisp_hand.session.open":
                return self._call(
                    self.runtime.open_session,
                    SessionOpenResultModel,
                    scope_type=arguments["scope_type"],
                    scope_target=arguments.get("scope_target"),
                    armed=arguments.get("armed"),
                    dry_run=arguments.get("dry_run"),
                    ttl_seconds=arguments.get("ttl_seconds"),
                )
            case "wisp_hand.session.close":
                return self._call(
                    self.runtime.close_session,
                    SessionCloseResultModel,
                    session_id=arguments["session_id"],
                )
            case "wisp_hand.desktop.get_topology":
                return self._call(
                    self.runtime.get_topology,
                    TopologyResultModel,
                    exclude_none=True,
                    detail=arguments.get("detail", "summary"),
                )
            case "wisp_hand.cursor.get_position":
                return self._call(
                    self.runtime.get_cursor_position,
                    CursorPositionResultModel,
                    session_id=arguments["session_id"],
                )
            case "wisp_hand.capture.screen":
                return self._call(
                    self.runtime.capture_screen,
                    CaptureResultModel,
                    session_id=arguments["session_id"],
                    target=arguments.get("target", "scope"),
                    inline=bool(arguments.get("inline", False)),
                    with_cursor=bool(arguments.get("with_cursor", False)),
                    downscale=arguments.get("downscale"),
                )
            case "wisp_hand.wait":
                return self._call(
                    self.runtime.wait,
                    WaitResultModel,
                    session_id=arguments["session_id"],
                    duration_ms=arguments["duration_ms"],
                )
            case "wisp_hand.capture.diff":
                return self._call(
                    self.runtime.capture_diff,
                    CaptureDiffResultModel,
                    left_capture_id=arguments["left_capture_id"],
                    right_capture_id=arguments["right_capture_id"],
                )
            case "wisp_hand.batch.run":
                return self._call(
                    self.runtime.batch_run,
                    BatchRunResultModel,
                    session_id=arguments["session_id"],
                    steps=arguments["steps"],
                    stop_on_error=bool(arguments.get("stop_on_error", True)),
                )
            case "wisp_hand.vision.describe":
                return self._call(
                    self.runtime.vision_describe,
                    VisionDescribeResultModel,
                    capture_id=arguments.get("capture_id"),
                    inline_image=arguments.get("inline_image"),
                    prompt=arguments.get("prompt"),
                )
            case "wisp_hand.vision.locate":
                return self._call(
                    self.runtime.vision_locate,
                    VisionLocateResultModel,
                    capture_id=arguments["capture_id"],
                    target=arguments["target"],
                )
            case "wisp_hand.pointer.move":
                return self._call(
                    self.runtime.pointer_move,
                    InputDispatchResultModel,
                    session_id=arguments["session_id"],
                    x=arguments["x"],
                    y=arguments["y"],
                )
            case "wisp_hand.pointer.click":
                return self._call(
                    self.runtime.pointer_click,
                    InputDispatchResultModel,
                    session_id=arguments["session_id"],
                    x=arguments["x"],
                    y=arguments["y"],
                    button=arguments.get("button", "left"),
                )
            case "wisp_hand.pointer.drag":
                return self._call(
                    self.runtime.pointer_drag,
                    InputDispatchResultModel,
                    session_id=arguments["session_id"],
                    start_x=arguments["start_x"],
                    start_y=arguments["start_y"],
                    end_x=arguments["end_x"],
                    end_y=arguments["end_y"],
                    button=arguments.get("button", "left"),
                )
            case "wisp_hand.pointer.scroll":
                return self._call(
                    self.runtime.pointer_scroll,
                    InputDispatchResultModel,
                    session_id=arguments["session_id"],
                    x=arguments["x"],
                    y=arguments["y"],
                    delta_x=arguments.get("delta_x", 0),
                    delta_y=arguments.get("delta_y", 0),
                )
            case "wisp_hand.keyboard.type":
                return self._call(
                    self.runtime.keyboard_type,
                    InputDispatchResultModel,
                    session_id=arguments["session_id"],
                    text=arguments["text"],
                )
            case "wisp_hand.keyboard.press":
                return self._call(
                    self.runtime.keyboard_press,
                    InputDispatchResultModel,
                    session_id=arguments["session_id"],
                    keys=arguments["keys"],
                )
            case _:
                return CallToolResult(
                    content=[TextContent(type="text", text=f"Unknown tool: {name}")],
                    isError=True,
                )

    async def _call_tool_as_task(self, experimental: Any, name: str, arguments: dict[str, Any]) -> CreateTaskResult:
        async def work(task) -> CallToolResult:
            # Task status messages are user-facing diagnostics for long-running work.
            # Keep them short, stable, and stage-based.
            try:
                await task.update_status("started")
                await task.update_status(f"running {name}")
            except Exception:  # pragma: no cover - best-effort status updates
                pass

            try:
                if name == "wisp_hand.wait":
                    normalized = await self._task_wait(task, arguments)
                else:
                    normalized = await anyio.to_thread.run_sync(lambda: self._call_sync_tool_by_name(name, arguments))
            except Exception as exc:  # pragma: no cover - defensive: task path must never crash the server
                normalized = CallToolResult(
                    content=[TextContent(type="text", text=f"internal_error: {exc}")],
                    structuredContent=None,
                    isError=True,
                )

            # Best-effort cancellation: if the task was cancelled while the work ran,
            # don't attempt to overwrite terminal state by completing.
            try:
                latest = await task._store.get_task(task.task_id)  # pyright: ignore[reportPrivateUsage]
            except Exception:  # pragma: no cover
                latest = None
            if latest is not None and getattr(latest, "status", None) == "cancelled":
                try:
                    task._ctx._task = latest  # pyright: ignore[reportPrivateUsage]
                except Exception:  # pragma: no cover
                    pass
                return normalized

            final_message = "error" if normalized.isError else "done"
            try:
                await task.update_status(final_message)
            except Exception:  # pragma: no cover
                pass

            # Complete the task here so the outer run_task wrapper won't attempt to
            # complete/fail again (which could crash the task group on races like cancel()).
            try:
                await task.complete(normalized)
            except Exception:
                # Most commonly: task was cancelled while running.
                # Keep task state terminal and swallow exceptions to avoid crashing TaskSupport.
                try:
                    latest = await task._store.get_task(task.task_id)  # pyright: ignore[reportPrivateUsage]
                    if latest is not None:
                        task._ctx._task = latest  # pyright: ignore[reportPrivateUsage]
                except Exception:  # pragma: no cover
                    pass

            return normalized

        return await experimental.run_task(work, model_immediate_response=f"running {name}")

    async def _task_wait(self, task: Any, arguments: dict[str, Any]) -> CallToolResult:
        session_id = arguments.get("session_id")
        duration_ms = arguments.get("duration_ms")
        if not isinstance(session_id, str) or not session_id:
            return CallToolResult(
                content=[TextContent(type="text", text="invalid_parameters: session_id must be a non-empty string")],
                isError=True,
            )
        if not isinstance(duration_ms, int):
            return CallToolResult(
                content=[TextContent(type="text", text="invalid_parameters: duration_ms must be an integer")],
                isError=True,
            )
        if duration_ms < 0:
            return CallToolResult(
                content=[TextContent(type="text", text="invalid_parameters: duration_ms must be >= 0")],
                isError=True,
            )

        # Validate session exists (fast, should not block the server loop).
        try:
            self.runtime._session_store.get_session(session_id)  # pyright: ignore[reportPrivateUsage]
        except WispHandError as exc:
            return self._result(exc.to_payload(), is_error=True)
        except Exception as exc:  # pragma: no cover
            return self._result(internal_error(str(exc)).to_payload(), is_error=True)

        started = anyio.current_time()
        remaining_ms = duration_ms
        while remaining_ms > 0:
            try:
                latest = await task._store.get_task(task.task_id)  # pyright: ignore[reportPrivateUsage]
            except Exception:  # pragma: no cover
                latest = None
            if latest is not None and getattr(latest, "status", None) == "cancelled":
                try:
                    task._ctx._task = latest  # pyright: ignore[reportPrivateUsage]
                except Exception:  # pragma: no cover
                    pass
                return CallToolResult(
                    content=[TextContent(type="text", text="cancelled")],
                    isError=True,
                )

            step_ms = min(50, remaining_ms)
            await anyio.sleep(step_ms / 1000.0)
            remaining_ms -= step_ms

        elapsed_ms = max(0, round((anyio.current_time() - started) * 1000))
        payload = WaitResultModel.model_validate(
            {"session_id": session_id, "duration_ms": duration_ms, "elapsed_ms": elapsed_ms}
        ).model_dump(mode="json")
        return self._result(payload)

    @staticmethod
    def _call(callback, response_model, /, *, exclude_none: bool = False, **kwargs) -> CallToolResult:
        try:
            payload = response_model.model_validate(callback(**kwargs)).model_dump(
                mode="json",
                exclude_none=exclude_none,
            )
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
