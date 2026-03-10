# Wisp Hand

一个面向 Hyprland/Wayland 的 computer-use MCP server 基座。它不是 agent，不做规划与决策，只提供可被外部 AI/客户端调用的库和 MCP 能力（观察、截图、输入、批处理、可选本地视觉、以及 task-augmented 的长耗时执行）。

## MCP

适用场景：

- 让 AI 帮你查看桌面应用状态（例如 Godot 编辑器）并执行少量输入
- 用 `capture + diff` 做 GUI 行为验证（动作前后是否发生变化）
- 以 session/scope 为安全边界做可审计的输入回放与排障

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

用 MCP Inspector 验证：

```bash
just inspector
```

启动文档站点（MkDocs）：

```bash
just docs-serve
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

### 核心概念：Session + Scope

Wisp Hand 的输入必须在 session 内执行，并且 session 绑定明确的 scope（作用域）。这让“截图/输入”都可以在同一套 scope-relative 坐标里闭环，且便于做安全与审计。

常用 scope：

- `window`：绑定某个窗口（推荐用于 Godot/IDE/浏览器等应用）
- `region`：绑定一个明确矩形区域（适合做局部验证与安全输入）

输入建议流程：

1. 先用 `armed=true, dry_run=true` 打开 session 校验坐标（尤其多显示器+缩放）。
2. 再用 `armed=true, dry_run=false` 进行真实输入。
3. 优先用 `capture.screen + capture.diff` 判断动作是否生效，而不是高频轮询 `desktop.get_topology`。

### 场景：让 AI 观察与操作 Godot

最小闭环建议拆成：

1. 获取 Godot 窗口 selector（切到 Godot 前台后读取 `desktop.get_topology` 的 `active_window`）
2. `session.open(scope_type="window", scope_target="<selector>")`
3. `capture.screen` 获取截图（必要时 `vision.locate` 辅助定位 Run/Play）
4. `pointer.click` 点击运行，`wait` 等待 UI 变化
5. 再 `capture.screen` 并用 `capture.diff` 做验证

更完整流程见文档：[docs/mkdocs/scenarios/godot.md](docs/mkdocs/scenarios/godot.md)。

### 坐标与缩放（重要）

- 对外输入坐标统一使用 Hyprland 的 layout/logical px（scope-relative）
- 截图尺寸是 image px（可能与 layout px 因 scale 不一致）
- runtime 会在 topology 中附带坐标映射信息，并通过自适应坐标后端处理混合缩放与多显示器场景

坐标诊断脚本：

```bash
uv run python examples/attempts/diagnose_coordinates.py --capture-check
```

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

### 文档

本仓库提供 MkDocs 文档站点（内容在 `docs/mkdocs/`）：

```bash
uv run mkdocs serve
uv run mkdocs build --strict
```

### 排障

见 [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md)。
