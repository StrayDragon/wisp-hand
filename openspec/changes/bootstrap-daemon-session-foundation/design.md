## Context

仓库当前只有最小 Python 包骨架，还没有任何可复用的 runtime contract。原始产品边界最初集中在一份单体 PRD 中，但后续 change 只有在这些公共契约稳定后才能独立推进。

这个 change 是整个 MVP 的唯一基础层。它不负责任何 Hyprland 读写能力，而是把后续所有功能都要共享的状态模型、错误模型和运行时目录约定一次定清。

## Goals / Non-Goals

**Goals:**

- 定义 daemon 与 MCP server 的逻辑边界和基础启动入口。
- 定义 session store、scope envelope、arming/dry-run/TTL 状态模型。
- 定义 runtime config、结构化错误和双通道日志/审计管线。
- 给下游 change 固定公共 API 形状，避免重复发明基础契约。

**Non-Goals:**

- 不实现 Hyprland 拓扑读取、截图、输入、batch、wait、diff 或 vision。
- 不为 X11、GNOME、KDE 或通用 Wayland 做兼容设计。
- 不在本 change 内引入面向用户的 GUI 或 overlay。

## Decisions

### 1. 采用“公共 runtime 先行”的拆分方式

先把 `hand.capabilities`、`hand.session.open`、`hand.session.close` 与公共状态模型固定，再让 observe/input/batch/vision 逐层挂到同一 runtime 上。这样后续 change 只新增能力，不改公共基座。

### 2. Session 是所有副作用与上下文的唯一载体

session 统一持有：

- `session_id`
- 标准化 scope envelope
- `armed`
- `dry_run`
- `expires_at`
- runtime metadata

后续任何需要上下文的工具都只接受 `session_id`，不重复携带另一套 scope 状态。

### 3. 能力探测与功能执行分离

`hand.capabilities` 负责一次性暴露环境可用性、缺失依赖和能力矩阵。这样下游工具可以专注执行逻辑，客户端也可以在实际调用前显式检查能力状态。

### 4. 结构化错误与 JSONL 审计是硬约束

错误码采用稳定 taxonomy，至少覆盖：

- `unsupported_environment`
- `dependency_missing`
- `capability_unavailable`
- `session_not_found`
- `session_expired`
- `policy_denied`

同时所有 tool call 都进入 JSONL 审计流，便于后续 input、batch、vision 直接复用，不再各自定义日志格式。

### 5. 运行时配置采用单一配置源

产品运行时配置与 OpenSpec 配置分离。OpenSpec 的 `openspec/config.yaml` 只约束提案生成；产品运行时仍使用单一配置文件承载目录、安全默认值、依赖策略和 provider 开关。

## Risks / Trade-offs

- 基础层先行会延后首个功能可见成果 -> 但可以显著减少后续 change 的公共接口返工。
- 现在就固定错误码与审计字段会增加前期设计成本 -> 但它是后续集成测试和调试的最低成本路径。
- 当前仓库是 Python 骨架，长期实现语言仍可能调整 -> 本 change 只固定逻辑边界与行为契约，不绑定具体实现语言。
