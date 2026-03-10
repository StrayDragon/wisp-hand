## Context

Wisp Hand 当前的可观测性主要由两部分组成：

- 结构化错误码与上下文字段（用于 tool call 返回）
- `AuditLogger` 写入的 `audit.jsonl`（机器可读）与 `runtime.log`（简要文本）

这套机制保证了“能追踪”，但在真实桌面验证与外部接入推进后暴露出两个痛点：

1. **日志可用性不足**：`runtime.log` 信息密度偏低且格式固定，外部接入方难以做聚合、检索与告警；开发时也缺少更适合交互式排障的输出形式。
2. **传输边界敏感**：当 MCP 使用 `stdio` transport 时，任何写入 stdout 的日志都会破坏协议；因此必须明确区分 stdout（协议数据）与 stderr/文件（日志）并让用户可配置。

本 change 只提升“日志/可观测性”这条横切能力，不改变 MCP 工具语义、不引入 agent loop。它位于 MVP change 链之后，建议在 `harden-mcp-beta-ready` 之前或并行落地，以便后续的 doctor/discovery、retention、smoke tests 都建立在统一日志基线之上。

## Goals / Non-Goals

**Goals:**

- 以 structlog 为核心统一 Wisp Hand 的日志事件模型，提供稳定字段与可选 JSON 输出，便于外部系统 ingest。
- 提供 Rich 控制台渲染，用于交互式调试时的可读性与错误栈输出，并确保 stdio transport 安全。
- 日志输出可配置：格式（json/rich/plain）、目标（文件/stderr）、级别、以及敏感字段的脱敏/截断策略。
- 明确并保持“审计 vs 运行日志”的边界：审计用于回放与归因，运行日志用于排障与运维；两者共享关联字段。

**Non-Goals:**

- 不新增/修改任何桌面动作工具（observe/input/batch/vision 的能力面不扩展）。
- 不实现日志上传、远程 telemetry、分布式追踪后端或 metrics 系统（Prometheus/OpenTelemetry 等）。
- 不引入与旧日志格式的双轨兼容 API；改造以统一事件模型为准，用户通过配置选择渲染与输出通道。

## Decisions

### 1. 单一“事件模型”，多渲染/多输出

所有 runtime 事件（启动、依赖探测、tool call 成功/失败/拒绝、关键子系统事件）都以 structlog 的事件字典为“唯一真源”。输出层只负责把同一事件渲染为：

- JSON Lines（面向 ingest）
- Rich Console（面向人类调试）
- Plain Text（作为极简回退）

这样避免“多套 logger 写不同内容”的漂移风险。

备选：继续保留独立的 audit writer + 自己拼文本 runtime.log。放弃原因是字段一致性与扩展性差，且无法满足可配置输出与 rich 渲染需求。

### 2. stdio transport 下强制 stdout 零日志

当 `server.transport=stdio` 时，任何日志输出 MUST 不写入 stdout。Rich/console handler 默认绑定到 stderr；文件 sink 默认写入 `paths.text_log_file` 或新定义的运行日志路径。

备选：允许 console 写 stdout。放弃原因是会破坏 MCP stdio 协议数据流。

### 3. 复用现有审计上下文作为关联维度来源

当前 runtime 已有 `_audit_context`（包含 batch_id、step_index、vision 输入来源等）。新的 structlog 事件会复用同一套上下文字段，以保证：

- 日志与审计能按同一维度关联
- batch/step 的父子关系不丢失

实现上可采用 contextvars/structlog 的上下文绑定，使“调用栈内自然携带字段”，而不是在每个 logger 调用点手工拼接。

### 4. 敏感字段默认脱敏，显式配置才能放开

输入链路（例如 `hand.keyboard.type` 的 `text`、vision 的 `inline_image`）可能包含敏感数据。默认策略为：

- 运行日志不记录原始敏感内容，只记录长度、hash 或摘要
- 审计日志保持可追踪但也做最小必要记录（例如保留 `text_length` 而非原文）

并提供配置开关，允许在本地调试场景放开（但需要用户显式启用）。

## Risks / Trade-offs

- 引入 `structlog`/`rich` 增加依赖与启动复杂度 → 通过单一事件模型 + 最小配置默认值降低心智负担。
- Rich 渲染在非交互环境可能干扰日志收集 → 默认在非 TTY 或 stdio 场景关闭 rich，或强制输出到 stderr。
- 结构化日志可能带来额外性能开销 → 通过 level 过滤、字段裁剪与避免序列化大对象控制开销。
- 脱敏策略若设计不当会降低排障信息 → 通过“默认安全 + 可配置放开”的方式平衡。

## Migration Plan

1. 新增 `logging/observability` 配置段并给出默认值（对齐当前 runtime.log/audit.jsonl 的基本能力）。
2. 在 CLI 启动阶段完成 logging 初始化，使 FastMCP 与 Wisp Hand runtime 都走同一套 logger 基线。
3. 将 `AuditLogger` 的文本日志输出迁移为 structlog 渲染结果；audit JSONL 可继续保留为独立文件（或由 structlog JSON sink 生成）。
4. 补齐文档与示例配置，提供 stdio 与网络 transport 的推荐日志配置。

## Open Questions

- 配置命名：使用 `[logging]` 还是 `[observability]` 作为顶层表，需要在实现前与现有 `server.log_level` 的边界一并确定。
- audit JSONL 是否要完全纳入 structlog JSON sink（统一输出），还是继续保留专用 `audit.jsonl`（语义更清晰但有两类文件）。
