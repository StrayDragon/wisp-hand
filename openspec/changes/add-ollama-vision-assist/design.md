## Context

到 `add-batch-wait-diff` 为止，系统已经具备完整的 deterministic computer-use 主链：foundation、observe、scoped input、batch/wait/diff 都可以独立工作。vision 是建立在这条主链之上的可选增强层，必须做到“关闭时零影响，开启后可追踪”。

因此本 change 不把视觉能力做成新的核心控制面，而是把它严格限定为 capture artifact 的消费者与辅助解释器。

## Goals / Non-Goals

**Goals:**

- 接入本地 Ollama provider，提供 describe / locate 两类视觉工具。
- 让视觉调用复用现有 capture artifact，而不是另起一套图像来源链路。
- 固定图像预处理、超时、并发限制与审计字段。
- 保证 vision 完全可选，关闭时不会影响其他 MCP 工具。

**Non-Goals:**

- 不实现云端模型、多 provider 路由或模型托管。
- 不实现危险动作前后的 `guard` 检查。
- 不让视觉能力绕过已有 session、scope、capture 与 audit 契约。

## Decisions

### 1. Vision 只消费 capture 或显式内联图像

`hand.vision.describe` 支持 `capture_id` 与 `inline_image`，`hand.vision.locate` 只接受 `capture_id`。这样 locate 的坐标结果天然落在已有 capture 元数据上下文里，后续若要做 locate-to-click，可以直接映射回 scope 坐标。

### 2. 先只做 Ollama 单 provider

本 change 只支持 Ollama HTTP API，不做 provider 抽象泛化。这样可以把超时、重试、并发、预处理和错误映射都直接对齐单一 provider，而不是为了未来扩展提前引入多后端复杂度。

### 3. Vision 是显式工具，不是隐式策略

当前只交付 `disabled` 与 `assist` 模式。视觉推理只在显式工具调用时发生，不会偷偷插入到输入链路里。危险动作前后的 `guard` 检查需要和策略引擎更紧密耦合，留到后续 hardening change。

### 4. 审计维度必须覆盖输入来源与模型开销

视觉调用除了普通 tool 审计字段外，还额外记录：

- 输入来源（capture / inline）
- capture_id
- provider / model
- latency
- 预处理尺寸

这样才能定位“是图像来源有问题，还是模型响应有问题”。

## Risks / Trade-offs

- Ollama 响应时延会显著高于 observe/input -> 通过超时、最大图像尺寸与并发限制控制上界。
- 只支持单 provider 会限制短期扩展性 -> 但它显著降低当前 change 的歧义与实现复杂度。
- `locate` 的候选框质量受模型能力影响 -> 通过保留 `reason`、`confidence` 和 capture 上下文，降低上层误用风险。
