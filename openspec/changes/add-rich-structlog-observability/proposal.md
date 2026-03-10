## Why

Wisp Hand 虽然已经具备审计 JSONL 与基础 runtime 文本日志，但当前可观测性偏“能用但不好用”：外部接入方难以稳定做日志聚合与检索，开发/调试时也缺少高信噪比的人类友好输出。随着 MCP 能力面完整与真实桌面实测推进，需要把日志体系升级为“结构化 + 可配置 + stdio 安全”的交付质量。

## What Changes

- 引入统一的结构化日志管线：所有 runtime 关键事件（启动、依赖探测、tool call、拒绝/错误、capture/vision 等）以 structlog 事件模型输出，提供稳定字段与层级。
- 引入 Rich 控制台日志渲染：在交互式调试场景提供更易读的 console 输出，并确保 stdio transport 下不会污染 MCP 协议输出。
- 扩展配置 schema：允许用户按场景选择日志格式（json / rich / plain）、输出目标（文件 / stderr）、级别、以及敏感字段的脱敏/截断策略。
- 明确“审计 vs 运行日志”的边界：审计仍以可回放/可追踪为目标，运行日志以排障/运维为目标；两者共享关键关联字段（tool、session、scope、latency、error code 等）。
- 完成定义：提供可复现的本地 smoke 验证路径，证明在 `stdio` 与网络 transport 下日志都可用且不影响协议；并能通过配置切换 json ingest 与 rich 调试两种模式。

## Capabilities

### New Capabilities

- `observability-logging`: 定义结构化日志事件、字段约束、输出通道与可配置策略，覆盖 stdio 安全、rich 渲染与 structlog JSON 输出。

### Modified Capabilities

无。

## Impact

- 影响 `wisp_hand` 的启动路径（CLI）、runtime 审计与日志写入路径，以及配置加载 schema。
- 引入新依赖：`structlog`、`rich`（仅用于日志输出，不改变现有 MCP 工具语义）。
- 会新增/调整文档与示例配置，以便外部 agent / client 与开发者在不同场景快速启用合适的日志模式。

