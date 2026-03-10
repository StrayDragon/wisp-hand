## Why

前面的 change 已经把 foundation、observe、scoped input、batch/wait/diff、vision 都做完了，但当前仓库还没有形成 beta-ready 的外部 MCP 集成契约：安装启动路径不完整、运行时自检不足、长时间运行下的日志/capture 体积治理缺失、外部 agent / client 也缺少稳定的接入与排障文档。

因此这次 change 不再新增桌面能力，而是把现有能力面打磨成“可安装、可发现、可诊断、可回归验证”的 MCP 交付物，作为 roadmap 中 `M6 hardening / beta-ready` 的正式落点。

## What Changes

- 新增 beta-ready 的 MCP 运行时发现与预检能力，覆盖版本、runtime instance、transport、启用能力、关键依赖与写路径状态，供外部 agent / client 在接入前显式探测。
- 新增运行时硬化与运维治理，覆盖 audit/capture retention、长期运行下的体积控制、重启后的 instance 识别与高并发/长会话边界。
- 为长耗时工具调用接入 MCP task-augmented execution：客户端可选择以 task 方式发起 `tools/call`，服务端立即返回 `CreateTaskResult`，后续通过 `tasks/get` / `tasks/result` 轮询结果，并支持 `tasks/cancel` 取消。
- 新增面向外部接入方的交付内容，包括安装/启动文档、推荐配置模板、stdio/网络 transport 的 smoke test 与故障排查路径。
- 收敛 MCP tool 命名空间前缀：将现有 `hand.*` 工具重命名为 `wisp_hand.*`，避免与其他 server 工具名冲突并提升语义清晰度（不做旧前缀兼容）。
- 明确本 change 的完成定义是“现有 MCP 能力可以被外部 agent / client 直接接入并稳定诊断”，而不是继续扩展新的 observe/input/vision 功能。
- 明确本 change 不实现内置 agent loop、不增加新的桌面动作原语、不做跨桌面兼容层。
- 依赖链位置：前置为 `add-ollama-vision-assist`；这是当前 roadmap 的 `M6`，完成后从 MVP change 链转入 beta 交付与后续 v1.1/maintenance 阶段。

## Capabilities

### New Capabilities
- `mcp-runtime-discovery`: 定义 beta-ready 的运行时发现、自检、版本/实例/transport 暴露与外部接入前探测契约。
- `mcp-task-augmented-execution`: 定义 tools/call 的 task-augmented 执行、轮询与取消契约，用于长耗时工具的稳定集成。
- `runtime-operations-hardening`: 定义 retention、实例关联、长期运行治理、重启后识别与运维清理边界。

### Modified Capabilities

无。

## Impact

- 影响 `wisp_hand.capabilities`（原 `hand.capabilities`）与所有 MCP tool 名称、CLI 启动/自检入口、配置 schema 与运行时元数据。
- 影响 audit/capture store 的 retention、清理与关联字段。
- 影响 README、安装说明、示例配置、外部 MCP smoke test 与故障排查文档。
- 为后续 beta 发布、外部 agent / client 集成和回归验证提供稳定基线。
