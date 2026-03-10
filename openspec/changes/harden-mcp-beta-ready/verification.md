## 验证记录（2026-03-10）

### 单元测试

```bash
uv run pytest -q
```

结果：`39 passed`

### OpenSpec 校验

```bash
openspec validate --type change harden-mcp-beta-ready --json
```

结果：`valid=true`

### Smoke（MCP 握手 + discovery + task-augmented）

stdio：

```bash
uv run python examples/attempts/smoke_mcp_transports.py --transport stdio --out /tmp/wisp-hand-mcp-smoke-stdio.json
```

sse：

```bash
uv run python examples/attempts/smoke_mcp_transports.py --transport sse --out /tmp/wisp-hand-mcp-smoke-sse.json
```

要点（两种 transport 一致）：

- `tools/list` 中 `wisp_hand.wait` 的 `execution.taskSupport == "optional"`
- `tools/call` 携带 `task` 元数据会立即返回 `CreateTaskResult`
- `tasks/get` 可轮询到 `statusMessage`（例如 `started/running/done`）
- `tasks/result` 可返回最终 `CallToolResult`

