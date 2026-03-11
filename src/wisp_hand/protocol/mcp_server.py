from __future__ import annotations

from typing import Any, cast

from mcp.server.fastmcp import FastMCP
from mcp.types import CallToolResult, TextContent

from wisp_hand.app.runtime import WispHandRuntime
from wisp_hand.infra.config import load_runtime_config
from wisp_hand.protocol.resources import register_resources
from wisp_hand.protocol.task_execution import TaskExecutionSupport
from wisp_hand.protocol.tool_registry import register_tools
from wisp_hand.shared.errors import WispHandError, internal_error


class WispHandServer(TaskExecutionSupport):
    def __init__(self, runtime: WispHandRuntime) -> None:
        self.runtime = runtime
        self.mcp = FastMCP(
            name="Wisp Hand",
            instructions="Hyprland-first computer-use MCP runtime foundation.",
            log_level=runtime.config.logging.level,
            host=runtime.config.server.host,
            port=runtime.config.server.port,
        )
        register_tools(self)
        register_resources(self)
        self._enable_task_augmented_execution()

    @staticmethod
    def _call(callback, response_model, /, *, exclude_none: bool = False, **kwargs) -> CallToolResult:
        try:
            payload = response_model.model_validate(callback(**kwargs)).model_dump(
                mode="json",
                exclude_none=exclude_none,
                by_alias=True,
            )
            return WispHandServer._result(payload)
        except WispHandError as exc:
            return WispHandServer._result(exc.to_payload(), is_error=True)
        except Exception as exc:
            return WispHandServer._result(internal_error(str(exc)).to_payload(), is_error=True)

    @staticmethod
    def _result(payload: dict[str, Any], *, is_error: bool = False) -> CallToolResult:
        if is_error:
            code = payload.get("code", "error")
            message = payload.get("message", "Error")
            text = f"{code}: {message}"
        else:
            text = "ok"

        max_len = 60
        if len(text) > max_len:
            text = text[: max_len - 3] + "..."

        return CallToolResult(
            content=[TextContent(type="text", text=text)],
            structuredContent=payload,
            isError=is_error,
        )

    def run(self, *, transport: str | None = None) -> None:
        self.mcp.run(transport=cast(str, transport or self.runtime.config.server.transport))


def create_server(runtime: WispHandRuntime | None = None) -> WispHandServer:
    return WispHandServer(runtime or WispHandRuntime(config=load_runtime_config()))
