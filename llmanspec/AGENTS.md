# llmanspec AGENTS.md

项目级上下文与代理指南。作为 `llmanspec/config.yaml` 的补充。

---

## 项目标识

| 字段 | 值 |
|---|---|
| 产品 | Wisp Hand |
| 定位 | Hyprland-first computer-use MCP runtime。不做 agent 规划/决策，只提供可被外部 AI/客户端调用的原子能力 |
| license | MIT |
| 语言 | Python ≥ 3.14 (CPython) |
| 包管理 | uv (>=0.10) |
| 运行时依赖 | `mcp[cli]`, `pillow`, `rich`, `structlog` |
| 核心 binary | `hyprctl`, `grim`, `slurp`（必须）；`wtype`（可选）；`ollama`（可选视觉） |
| transport | stdio / sse / streamable-http |
| 版本 | 0.1.x (beta) |

## 架构总览

### 包结构 (`src/wisp_hand/`)

```
wisp_hand/
├── __init__.py          # 空
├── __main__.py          # python -m wisp_hand
├── cli.py               # CLI 入口 (wisp-hand doctor / mcp)
├── mcp_app.py           # 快速启动入口（剥离中）
├── tooling.py           # 遗留工具
│
├── app/                 # 应用装配层
│   ├── bootstrap.py     # 启动编排
│   └── runtime.py       # WispHandRuntime — 核心 runtime，组合所有 service
│
├── protocol/            # MCP 协议层（与 domain service 隔离）
│   ├── mcp_server.py    # FastMCP server 创建、tool/resource 注册
│   ├── tool_registry.py # tool 注册（将 runtime 方法暴露为 MCP tool）
│   ├── resources.py     # MCP Resources 注册（capture png / json 按需读取）
│   └── task_execution.py# Task-Augmented Execution（长耗时 tools/call）
│
├── session/             # session 生命周期 + scope envelope
│   ├── models.py        # ScopeEnvelope, SessionOpenResult, SessionCloseResult
│   ├── service.py       # SessionService（open/close/validate）
│   └── store.py         # SessionStore（TTL 守卫、并发安全）
│
├── desktop/             # Hyprland 桌面观察
│   ├── models.py        # 桌面拓扑数据模型
│   ├── hyprland_adapter.py # Hyprland IPC（hyprctl/jq 封装）
│   ├── scope.py         # scope 标准化（region/window/desktop）
│   └── service.py       # DesktopService（topology / cursor / window 查询）
│
├── capture/             # 截图 + artifact store + diff
│   ├── models.py        # CaptureResult, CaptureDiffResult
│   ├── service.py       # CaptureService
│   ├── store.py         # CaptureArtifactStore（基于文件 + retention）
│   ├── diff.py          # CaptureDiffEngine（像素级差异）
│   └── uris.py          # MCP Resource URI 构造
│
├── input/               # scoped pointer / keyboard 输入
│   ├── models.py        # InputDispatchResult, PointerButton
│   ├── service.py       # InputService（scope 校验 → 坐标映射 → dispatch）
│   ├── backend.py       # WaylandInputBackend（wtype + ydotool）
│   └── policy.py        # InputPolicy（emergency stop, rate limit, dangerous shortcuts）
│
├── batch/               # 批处理编排
│   ├── models.py        # BatchRunResult, WaitResult
│   └── service.py       # BatchService（步骤编排 + fail-fast）
│
├── vision/              # 本地 Ollama 视觉辅助
│   ├── models.py        # VisionDescribeResult, VisionLocateResult
│   ├── service.py       # VisionService
│   └── provider.py      # OllamaVisionProvider（HTTP 请求 + 图像预处理）
│
├── coordinates/         # 坐标映射后端
│   ├── models.py        # CoordinateMap, PixelRatio
│   ├── service.py       # CoordinateService（auto/hyprctl-infer/grim-probe）
│   ├── backends.py      # 各坐标后端实现
│   ├── cache.py         # 坐标缓存（topology_fingerprint 失效）
│   └── fingerprint.py   # 拓扑指纹生成
│
├── capabilities/        # 能力自检
│   ├── models.py        # CapabilityResult
│   └── service.py       # CapabilitiesService
│
├── infra/               # 基础设施（共享于所有 domain）
│   ├── config.py        # RuntimeConfig — pydantic 统一配置（TOML）
│   ├── audit.py         # AuditLogger（JSONL 审计记录）
│   ├── observability.py # structlog 初始化 + 日志配置
│   ├── discovery.py     # runtime preflight / discovery
│   └── command.py       # CommandRunner（子进程封装）
│
└── shared/              # 跨域共享类型
    ├── types.py         # JSONValue 类型别名
    └── errors.py        # WispHandError + ErrorPayload + MCP_ERROR_MAP
```

### 核心架构模式

- **Runtime 是装配层，不是能力聚合层**：`WispHandRuntime` 在 `app/runtime.py` 中组合所有 domain service，不直接承载领域逻辑。每个 domain service 只通过构造参数接收依赖（显式 DI）。
- **协议与领域隔离**：`protocol/` 负责 FastMCP 注册、tool surface 适配和 task execution；domain service 对 MCP 协议对象零依赖，只返回领域结果/结构化错误。
- **结构化错误**：所有失败通过 `WispHandError` 抛出，带有 stable error code（`MCP_ERROR_MAP` 映射到 MCP JSON-RPC error code）和结构化 `details`。

## 设计原则

1. **Hyprland-first** — v1 不做 X11/GNOME/KDE/通用 Wayland 兼容层
2. **Scope-first** — 所有副作用动作必须显式绑定 session scope
3. **Deterministic-first** — 优先低级、明确、可验证工具
4. **Safe-by-default** — 默认 disarmed，所有输入受策略 + 审计约束
5. **Local-first** — 视觉默认本地 Ollama，允许完全关闭
6. **Observable-first** — tool call / capture / action / rejection / latency 全部可追踪
7. **Token-efficient** — `content` 只返回极短摘要（成功 `ok`；失败 `code: message`）；完整结果走 `structuredContent`；重内容走 MCP Resources 按需读取

## 安全模型

```
session (open)
  ├── armed=false ───────────────────→ observe 类工具可调用，输入工具被拒绝 (session_not_armed)
  ├── armed=true + dry_run=true ─────→ 输入链路完整校验 + 审计，但不实际 dispatch
  └── armed=true + dry_run=false ───→ 真实输入

所有输入工具（pointer.* / keyboard.*）共享：
  - session 存在性 + 过期检查
  - scope 边界校验（越界 → scope_violation）
  - emergency stop（锁存，触发后所有输入被拒绝 → policy_denied）
  - 频率限制（超最大动作数 → policy_denied）
  - 危险快捷键阻止（policy_denied）
```

## session + scope 生命周期

```
1. session.open(scope_type, scope_target, armed, dry_run, ttl)
   → 返回 session_id + 标准化 scope envelope + expires_at

2. 后续 observe/input/batch/vision 工具通过 session_id 绑定同一 scope

3. session.close(session_id) → 使 session_id 不可用
   或 TTL 到期 → 自动失效（session_expired）

scope 类型：
  - "desktop" — 全桌面
  - "monitor" — 特定显示器
  - "window" — 绑定窗口（通过 selector: address/class/title）
  - "region" — 矩形区域
```

## MCP tool 命名空间 (`wisp_hand.*`)

| Tool | 模块 | spec 引用 |
|---|---|---|
| `wisp_hand.capabilities` | capabilities | `session-runtime` r1 |
| `wisp_hand.session.open` | session | `session-runtime` r2 |
| `wisp_hand.session.close` | session | `session-runtime` r2 |
| `wisp_hand.desktop.get_topology` | desktop | `hyprland-topology-observe` r1 |
| `wisp_hand.desktop.get_active_window` | desktop | `hyprland-topology-observe` r1 |
| `wisp_hand.desktop.get_monitors` | desktop | `hyprland-topology-observe` r1 |
| `wisp_hand.desktop.list_windows` | desktop | `hyprland-topology-observe` r1 |
| `wisp_hand.cursor.get_position` | desktop | `hyprland-topology-observe` r2 |
| `wisp_hand.capture.screen` | capture | `screen-capture-artifacts` r1, r2 |
| `wisp_hand.capture.diff` | capture | `state-wait-and-diff` r2 |
| `wisp_hand.wait` | batch | `state-wait-and-diff` r1 |
| `wisp_hand.batch.run` | batch | `action-batch-runner` r1-r3 |
| `wisp_hand.pointer.move` | input | `scoped-input-control` r1 |
| `wisp_hand.pointer.click` | input | `scoped-input-control` r1 |
| `wisp_hand.pointer.drag` | input | `scoped-input-control` r1 |
| `wisp_hand.pointer.scroll` | input | `scoped-input-control` r1 |
| `wisp_hand.keyboard.type` | input | `scoped-input-control` r2 |
| `wisp_hand.keyboard.press` | input | `scoped-input-control` r2 |
| `wisp_hand.vision.describe` | vision | `ollama-vision-assist` r2 |
| `wisp_hand.vision.locate` | vision | `ollama-vision-assist` r3 |

为减少 token 消耗，所有 tool 返回遵循 `mcp-token-efficient-surface` 规范：
- `structuredContent` 承载完整结果，`content` 默认极短文本 `ok` 或 `code: message`
- 截图通过 MCP Resources (`wisp-hand://captures/{id}.png` / `.json`) 按需读取

## 坐标系统

- **输入坐标**：layout/logical px（scope-relative，与 Hyprland `hyprctl` 输出一致）
- **截图尺寸**：image px（可能与 layout px 因 HiDPI scale 不一致）
- **坐标后端**：`CoordinateService` 支持 `auto/hyprctl-infer/grim-probe/active-pointer-probe`
- **拓扑指纹**：`topology_fingerprint` 用于坐标缓存失效判断
- `detail=summary` topoloty 返回 `coordinate_backend` + `desktop_layout_bounds` + `monitors[*].pixel_ratio`

## 配置分层

```
1. 默认值（pydantic BaseModel Field default）
   ↓ 合并
2. TOML config 文件（默认 ~/.config/wisp-hand/config.toml）
   ↓ 环境变量覆盖
3. WISP_HAND_CONFIG（自定义配置路径）
   ↓ CLI 覆盖
4. --config / --transport
```

配置变更时同步更新 `docs/example_config.toml`。

## 测试约定

```
tests/
├── batch/          # BatchService 单元 + 集成
├── capture/        # CaptureService + store + diff
├── desktop/        # DesktopService + topology
├── input/          # InputService + policy
├── integration/    # CLI / MCP 外部接口稳定性
├── protocol/       # tool_registry + resources + task_execution
├── session/        # SessionService + store
└── vision/         # VisionService + provider
```

- 测试文件命名：`test_<module>.py`
- 使用 `pytest` 标准 fixture + dependency injection（`WispHandRuntime` 构造参数可注入 mock）
- 集成测试验证 CLI/MCP 外部接口行为（`test_*.py` in `tests/integration/`）
- tool call 失败路径必须覆盖 `error_payload(code, message, details)`

## CLI 入口

```
wisp-hand
  ├── doctor [--json] [--config PATH]    # preflight 检查
  └── mcp [--config PATH] [--transport {stdio|sse|streamable-http}]
```

- `doctor --json` 输出机器可读的 discovery report（非零退出表示阻塞问题）
- `mcp` 启动前自动执行 preflight，阻塞问题阻止启动
- 等价的 `python -m wisp_hand mcp --config ...` / `uv run wisp-hand mcp --config ...`

## 开发常用命令

```bash
just doctor            # preflight 检查（需 jq）
just serve             # 启动 MCP server（默认 stdio）
just inspector         # MCP Inspector UI
just docs-serve        # MkDocs 文档站点
just docs-build        # 构建文档站点
just version           # 查看版本
just bump-version      # 版本 bump
uv run pytest          # 运行测试
uv run pytest -k <filter>  # 运行特定测试
```

## 结构化错误码

| Code | JSON-RPC code | 说明 |
|---|---|---|
| `invalid_config` | -32602 | 配置非法 |
| `invalid_parameters` | -32602 | 参数错误 |
| `invalid_scope` | -32602 | scope 无效 |
| `unsupported_environment` | -32001 | 非 Hyprland |
| `dependency_missing` | -32002 | 关键依赖缺失 |
| `capability_unavailable` | -32003 | 能力不可用 |
| `session_not_found` | -32004 | session 不存在 |
| `session_expired` | -32005 | session 已过期 |
| `policy_denied` | -32006 | 策略拒绝 |
| `session_not_armed` | -32007 | session 未 armed |
| `scope_violation` | -32008 | 越界 |
| `internal_error` | -32603 | 内部错误 |

<!-- Add your rules below this line -->
