## Wisp Hand MCP

一个面向 Hyprland/Wayland 的 computer-use MCP server 基座。它不是 agent，本项目只提供可被 agent 调用的 MCP 能力（观察、截图、输入、批处理、可选本地视觉、以及 task-augmented 的长耗时执行）。

### 快速开始

推荐先做连接前自检：

```bash
uvx wisp-hand-mcp doctor --json
```

启动（默认 `stdio` transport）：

```bash
uvx wisp-hand-mcp --config ~/.config/wisp-hand/config.toml
```

开发/调试（等价入口）：

```bash
uv run wisp-hand-mcp --config ./config.toml
python -m wisp_hand --config ./config.toml
```

### 工具概览（MCP tools）

工具命名空间固定为 `wisp_hand.*`：

- 发现与基础：`wisp_hand.capabilities`、`wisp_hand.session.open`、`wisp_hand.session.close`
- 只读观察：`wisp_hand.desktop.get_topology`、`wisp_hand.cursor.get_position`
- 截图与对比：`wisp_hand.capture.screen`、`wisp_hand.capture.diff`（capture artifact store: `png + json metadata`）
- 批处理与等待：`wisp_hand.batch.run`、`wisp_hand.wait`
- 可选本地视觉：`wisp_hand.vision.describe` / `wisp_hand.vision.locate`（Ollama，可关闭）
- Scoped 输入：`wisp_hand.pointer.*`、`wisp_hand.keyboard.*`

安全默认值：

- 新 session 默认 `armed=false`，未 armed 的输入会被拒绝
- 组合键策略会拒绝危险快捷键（并进入 audit/log）
- 默认脱敏：`keyboard.type` 文本、`inline_*` base64 等不会以明文进入日志/审计（可配置放开）

### 坐标与缩放（重要）

- 对外输入坐标统一使用 Hyprland 的 layout/logical px（scope-relative）
- 截图尺寸是 image px（可能与 layout px 因 scale 不一致）
- runtime 会在 topology 中附带坐标映射信息，并通过自适应坐标后端处理混合缩放与多显示器场景

### Task-Augmented Execution（长耗时调用）

当客户端在 `tools/call` params 里携带 `task` 元数据时，服务会立即返回 `CreateTaskResult`，并在后台执行，客户端可用 `tasks/get` 轮询、用 `tasks/result` 获取最终 `CallToolResult`，也可 `tasks/cancel` 取消。

可参考 smoke 脚本：

- `uv run python examples/attempts/smoke_mcp_transports.py --transport stdio`
- `uv run python examples/attempts/smoke_mcp_transports.py --transport sse`

### 配置示例（`config.toml`）

默认配置路径：`~/.config/wisp-hand/config.toml`（也可用环境变量 `WISP_HAND_CONFIG` 或 CLI `--config` 指定）

```toml
[server]
transport = "stdio"          # stdio | sse | streamable-http
host = "127.0.0.1"
port = 8000

[paths]
state_dir = "~/.local/state/wisp-hand"
audit_file = "~/.local/state/wisp-hand/audit.jsonl"
runtime_log_file = "~/.local/state/wisp-hand/runtime.jsonl"
# capture_dir 如不显式指定，默认在 state_dir/captures

[logging]
level = "INFO"
allow_sensitive = false

[logging.console]
enabled = true
format = "rich"              # rich | plain | json

[logging.file]
enabled = true
format = "json"              # json | plain | rich(会自动降级)

[retention.captures]
max_age_seconds = 604800      # 7d
max_total_bytes = 268435456   # 256MB

[retention.audit]
max_bytes = 10485760
backup_count = 5

[retention.runtime_log]
max_bytes = 10485760
backup_count = 5

[vision]
mode = "disabled"            # disabled | assist
base_url = "http://127.0.0.1:11434"
model = "qwen3.5:0.8b"
timeout_seconds = 30

[coordinates]
mode = "auto"                # auto | hyprctl-infer | grim-probe | active-pointer-probe
cache_enabled = true
probe_region_size = 120
min_confidence = 0.75
```

### 排障

见 [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md)。
