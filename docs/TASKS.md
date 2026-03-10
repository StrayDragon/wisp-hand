## Task-Augmented Execution（任务模式）

当你要调用可能耗时的工具（例如 `wait`、`batch`、`vision`、截图等），建议使用 MCP 的 task-augmented 模式：

- `tools/call` 请求里带上 `task` 元数据
- 服务端会立刻返回 `CreateTaskResult`（包含 `taskId`）
- 之后通过：
  - `tasks/get` 查询状态（看 `status` / `statusMessage` / `pollInterval`）
  - `tasks/result` 获取最终 payload（对 `tools/call` 来说是 `CallToolResult`）
  - `tasks/cancel` 取消未终态任务

### Python 示例（stdio）

```python
import anyio
import mcp.types as types
from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client


async def main():
    server = StdioServerParameters(command="wisp-hand-mcp", args=["--config", "/path/to/config.toml"])
    async with stdio_client(server) as (r, w):
        async with ClientSession(r, w) as session:
            await session.initialize()

            opened = await session.call_tool("wisp_hand.session.open", {"scope_type": "desktop"})
            session_id = opened.structuredContent["session_id"]

            created = await session.experimental.call_tool_as_task(
                "wisp_hand.wait",
                {"session_id": session_id, "duration_ms": 2000},
                ttl=60_000,
            )
            task_id = created.task.taskId

            async for status in session.experimental.poll_task(task_id):
                print(status.status, status.statusMessage)

            result = await session.experimental.get_task_result(task_id, types.CallToolResult)
            print(result.structuredContent)


anyio.run(main)
```

### 建议策略

- `ttl`：建议至少覆盖一次工具的最坏耗时，并为排障留余量（默认客户端通常是 60s）。
- 轮询：优先使用 `pollInterval`（服务端会给出建议值），并对网络 transport 做退避。
- 取消：`tasks/cancel` 是 best-effort。任务进入 `cancelled` 后服务端不会再把它变回 `completed/failed`。

