<p align="center">
  <img src="https://raw.githubusercontent.com/StrayDragon/wisp-hand/main/docs/assets/logo.webp" alt="Wisp Hand" width="180" />
</p>

<p align="center">
  <a href="https://pypi.org/project/wisp-hand/"><img alt="PyPI" src="https://img.shields.io/pypi/v/wisp-hand.svg"></a>
  <a href="https://pypi.org/project/wisp-hand/"><img alt="Python" src="https://img.shields.io/pypi/pyversions/wisp-hand.svg"></a>
  <a href="https://github.com/StrayDragon/wisp-hand/actions/workflows/ci.yaml"><img alt="CI" src="https://github.com/StrayDragon/wisp-hand/actions/workflows/ci.yaml/badge.svg"></a>
  <a href="https://github.com/StrayDragon/wisp-hand/actions/workflows/deploy-pages.yaml"><img alt="Pages" src="https://github.com/StrayDragon/wisp-hand/actions/workflows/deploy-pages.yaml/badge.svg"></a>
  <a href="https://github.com/StrayDragon/wisp-hand/blob/main/LICENSE"><img alt="License" src="https://img.shields.io/github/license/StrayDragon/wisp-hand.svg"></a>
</p>

<p align="center">
  <img alt="MCP" src="https://img.shields.io/badge/MCP-fastmcp-informational">
  <img alt="Hyprland" src="https://img.shields.io/badge/Hyprland-only-111111">
  <img alt="Wayland" src="https://img.shields.io/badge/Wayland-OK-0aa?logo=wayland&logoColor=white">
  <img alt="uv" src="https://img.shields.io/badge/uv-0.10+-2f2f2f">
  <img alt="structlog" src="https://img.shields.io/badge/structlog-logging-2f2f2f">
  <img alt="rich" src="https://img.shields.io/badge/rich-console-2f2f2f">
</p>

# Wisp Hand

一个面向 Hyprland/Wayland 的 computer-use MCP runtime。它不做 agent 的规划与决策，只提供可被外部 AI/客户端调用的能力：观察、截图、对比、输入、批处理、可选本地视觉，以及面向耗时任务的 task-augmented 执行。

适合用来做：

- 让 AI 帮你查看桌面应用状态（例如 Godot 编辑器）并执行少量输入
- 用 `capture + diff` 做 GUI 行为验证（动作前后是否发生变化）
- 以 session/scope 为安全边界做可审计的输入回放与排障

## 快速开始

连接前自检：

```bash
uvx wisp-hand doctor --json | jq .
```

启动（默认 `stdio` transport）：

```bash
uvx wisp-hand mcp --config ~/.config/wisp-hand/config.toml
```

开发/调试（等价入口）：

```bash
uv run wisp-hand mcp --config ./config.toml
python -m wisp_hand mcp --config ./config.toml
```

用 MCP Inspector 验证：

```bash
just inspector
```

启动文档站点（MkDocs）：

```bash
just docs-serve
```

## 工具概览（MCP tools）

工具命名空间固定为 `wisp_hand.*`：

- 发现与基础：`wisp_hand.capabilities`、`wisp_hand.session.open`、`wisp_hand.session.close`
- 只读观察：`wisp_hand.desktop.get_active_window`、`wisp_hand.desktop.get_monitors`、`wisp_hand.desktop.list_windows`、`wisp_hand.desktop.get_topology`、`wisp_hand.cursor.get_position`
- 截图与对比：`wisp_hand.capture.screen`、`wisp_hand.capture.diff`（capture artifact store: `png + json metadata`，默认走 MCP resources）
- 批处理与等待：`wisp_hand.batch.run`、`wisp_hand.wait`
- 可选本地视觉：`wisp_hand.vision.describe` / `wisp_hand.vision.locate`（Ollama，可关闭）
- Scoped 输入：`wisp_hand.pointer.*`、`wisp_hand.keyboard.*`

默认 token-efficient：

- tool result 的 `content` 只返回极短摘要（成功 `ok`；失败 `code: message`），完整结果只在 `structuredContent`。
- `wisp_hand.capture.screen` 默认不把 `png/base64/path` 塞进 tool result，而是返回 `image_uri`/`metadata_uri`，让客户端按需 `resources/read` 拉取。
- `wisp_hand.desktop.get_topology` 支持 `detail=summary|full|raw`，默认 `summary`（不返回 `windows` 列表）。排障时再用 `full/raw`。

安全默认值：

- 新 session 默认 `armed=false`，输入类工具会被拒绝
- 危险快捷键会被策略拒绝（并进入 audit/log）
- 默认脱敏：`keyboard.type` 文本等不会以明文进入日志/审计（可配置放开）

## 核心概念：Session + Scope

Wisp Hand 的输入必须在 session 内执行，并且 session 绑定明确的 scope（作用域）。截图/输入都用同一套 scope-relative 坐标闭环，方便安全控制与审计。

常用 scope：

- `window`：绑定某个窗口（推荐用于 Godot/IDE/浏览器等应用）
- `region`：绑定一个明确矩形区域（适合做局部验证与安全输入）

输入建议流程：

1. 先用 `armed=true, dry_run=true` 打开 session 校验坐标（尤其多显示器+缩放）。
2. 再用 `armed=true, dry_run=false` 进行真实输入。
3. 优先用 `capture.screen + capture.diff` 判断动作是否生效，而不是高频轮询 `desktop.get_topology`。

## 场景：让 AI 观察与操作 Godot

最小闭环建议拆成：

1. 获取 Godot 窗口 selector（切到 Godot 前台后读取 `desktop.get_active_window`）
2. `session.open(scope_type="window", scope_target="<selector>")`
3. `capture.screen` 获取截图（必要时 `vision.locate` 辅助定位 Run/Play）
4. `pointer.click` 点击运行，`wait` 等待 UI 变化
5. 再 `capture.screen` 并用 `capture.diff` 做验证

更完整流程见文档：[docs/mkdocs/scenarios/godot.md](docs/mkdocs/scenarios/godot.md)。

## 坐标与缩放（重要）

- 对外输入坐标统一使用 Hyprland 的 layout/logical px（scope-relative）
- 截图尺寸是 image px（可能与 layout px 因 scale 不一致）
- runtime 会在 topology 中附带坐标映射信息，并通过自适应坐标后端处理混合缩放与多显示器场景

坐标诊断脚本：

```bash
uv run python examples/attempts/diagnose_coordinates.py --capture-check
```

## Task-Augmented Execution（长耗时调用）

当客户端在 `tools/call` params 里携带 `task` 元数据时，服务会立即返回 `CreateTaskResult`，并在后台执行，客户端可用 `tasks/get` 轮询、用 `tasks/result` 获取最终 `CallToolResult`，也可 `tasks/cancel` 取消。

可参考 smoke 脚本：

- `uv run python examples/attempts/smoke_mcp_transports.py --transport stdio`
- `uv run python examples/attempts/smoke_mcp_transports.py --transport sse`

## 配置示例（`config.toml`）

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

## 文档

本仓库提供 MkDocs 文档站点（内容在 `docs/mkdocs/`）：

```bash
uv run mkdocs serve
uv run mkdocs build --strict
```

## 排障

见 [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md)。
