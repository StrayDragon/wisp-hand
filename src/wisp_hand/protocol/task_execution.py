from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import anyio
from mcp.types import CallToolResult, ContentBlock, CreateTaskResult, TASK_OPTIONAL, TextContent, Tool, ToolExecution

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
from wisp_hand.session.models import SessionCloseResultModel, SessionOpenResultModel
from wisp_hand.shared.errors import WispHandError, internal_error
from wisp_hand.vision.models import VisionDescribeResultModel, VisionLocateResultModel


class TaskExecutionSupport:
    def _enable_task_augmented_execution(self) -> None:
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
        except LookupError:
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
        if isinstance(result, dict):
            return CallToolResult(
                content=[TextContent(type="text", text="ok")],
                structuredContent=result,
                isError=False,
            )
        if isinstance(result, tuple) and len(result) == 2:
            unstructured, structured = result
            if not isinstance(structured, dict):
                raise TypeError("Structured tool result must be a dict")
            return CallToolResult(content=list(unstructured), structuredContent=structured, isError=False)
        if isinstance(result, Sequence):
            return CallToolResult(content=list(result), structuredContent=None, isError=False)
        raise TypeError(f"Unexpected tool return type: {type(result).__name__}")

    def _call_sync_tool_by_name(self, name: str, arguments: dict[str, Any]) -> CallToolResult:
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
                return self._call(self.runtime.close_session, SessionCloseResultModel, session_id=arguments["session_id"])
            case "wisp_hand.desktop.get_topology":
                return self._call(
                    self.runtime.get_topology,
                    TopologyResultModel,
                    exclude_none=True,
                    detail=arguments.get("detail", "summary"),
                )
            case "wisp_hand.desktop.get_active_window":
                return self._call(self.runtime.get_active_window, ActiveWindowResultModel, exclude_none=True)
            case "wisp_hand.desktop.get_monitors":
                return self._call(self.runtime.get_monitors, MonitorsResultModel, exclude_none=True)
            case "wisp_hand.desktop.list_windows":
                return self._call(
                    self.runtime.list_windows,
                    WindowsListResultModel,
                    exclude_none=True,
                    limit=arguments.get("limit", 50),
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
                    exclude_none=True,
                    session_id=arguments["session_id"],
                    steps=arguments["steps"],
                    stop_on_error=bool(arguments.get("stop_on_error", True)),
                    return_mode=arguments.get("return_mode", "summary"),
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
                    exclude_none=True,
                    capture_id=arguments["capture_id"],
                    target=arguments["target"],
                    limit=arguments.get("limit", 3),
                    space=arguments.get("space", "scope"),
                )
            case "wisp_hand.pointer.move":
                return self._call(self.runtime.pointer_move, InputDispatchResultModel, session_id=arguments["session_id"], x=arguments["x"], y=arguments["y"])
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
                return self._call(self.runtime.keyboard_type, InputDispatchResultModel, session_id=arguments["session_id"], text=arguments["text"])
            case "wisp_hand.keyboard.press":
                return self._call(self.runtime.keyboard_press, InputDispatchResultModel, session_id=arguments["session_id"], keys=arguments["keys"])
            case _:
                return self._result(WispHandError("invalid_parameters", f"Unknown tool: {name}").to_payload(), is_error=True)

    async def _call_tool_as_task(self, experimental: Any, name: str, arguments: dict[str, Any]) -> CreateTaskResult:
        async def work(task) -> CallToolResult:
            try:
                await task.update_status("started")
                await task.update_status(f"running {name}")
            except Exception:
                pass

            try:
                if name == "wisp_hand.wait":
                    normalized = await self._task_wait(task, arguments)
                else:
                    normalized = await anyio.to_thread.run_sync(lambda: self._call_sync_tool_by_name(name, arguments))
            except Exception as exc:
                normalized = self._result(internal_error(str(exc)).to_payload(), is_error=True)

            try:
                latest = await task._store.get_task(task.task_id)  # pyright: ignore[reportPrivateUsage]
            except Exception:
                latest = None
            if latest is not None and getattr(latest, "status", None) == "cancelled":
                try:
                    task._ctx._task = latest  # pyright: ignore[reportPrivateUsage]
                except Exception:
                    pass
                return normalized

            final_message = "error" if normalized.isError else "done"
            try:
                await task.update_status(final_message)
            except Exception:
                pass

            try:
                await task.complete(normalized)
            except Exception:
                try:
                    latest = await task._store.get_task(task.task_id)  # pyright: ignore[reportPrivateUsage]
                    if latest is not None:
                        task._ctx._task = latest  # pyright: ignore[reportPrivateUsage]
                except Exception:
                    pass

            return normalized

        return await experimental.run_task(work, model_immediate_response=f"running {name}")

    async def _task_wait(self, task: Any, arguments: dict[str, Any]) -> CallToolResult:
        session_id = arguments.get("session_id")
        duration_ms = arguments.get("duration_ms")
        if not isinstance(session_id, str) or not session_id:
            return self._result(WispHandError("invalid_parameters", "session_id must be a non-empty string").to_payload(), is_error=True)
        if not isinstance(duration_ms, int):
            return self._result(WispHandError("invalid_parameters", "duration_ms must be an integer").to_payload(), is_error=True)
        if duration_ms < 0:
            return self._result(WispHandError("invalid_parameters", "duration_ms must be >= 0").to_payload(), is_error=True)

        try:
            self.runtime._session_store.get_session(session_id)  # pyright: ignore[reportPrivateUsage]
        except WispHandError as exc:
            return self._result(exc.to_payload(), is_error=True)
        except Exception as exc:
            return self._result(internal_error(str(exc)).to_payload(), is_error=True)

        started = anyio.current_time()
        remaining_ms = duration_ms
        while remaining_ms > 0:
            try:
                latest = await task._store.get_task(task.task_id)  # pyright: ignore[reportPrivateUsage]
            except Exception:
                latest = None
            if latest is not None and getattr(latest, "status", None) == "cancelled":
                try:
                    task._ctx._task = latest  # pyright: ignore[reportPrivateUsage]
                except Exception:
                    pass
                return CallToolResult(content=[TextContent(type="text", text="cancelled")], isError=True)

            step_ms = min(50, remaining_ms)
            await anyio.sleep(step_ms / 1000.0)
            remaining_ms -= step_ms

        elapsed_ms = max(0, round((anyio.current_time() - started) * 1000))
        payload = WaitResultModel.model_validate(
            {"session_id": session_id, "duration_ms": duration_ms, "elapsed_ms": elapsed_ms}
        ).model_dump(mode="json")
        return self._result(payload)
