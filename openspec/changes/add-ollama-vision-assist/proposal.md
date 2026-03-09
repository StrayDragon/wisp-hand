## Why

前面的 change 已经把 foundation、observe、input、batch/wait/diff 链路都立住了，但 agent 仍然只能依赖显式坐标与截图自己推断界面意义。要让 `Wisp Hand` 成为面向 AI agent 的 computer-use 基础设施，还需要一层可选、可关闭、完全本地的视觉辅助能力。

这个 change 把 vision 严格定义为“建立在 capture artifact 之上的可选辅助层”，而不是让视觉能力反向改写底层 runtime 或安全边界。

## What Changes

- 新增 Ollama provider 集成，支持基于本地 HTTP API 的图像描述与目标定位。
- 暴露 `hand.vision.describe` 与 `hand.vision.locate` 两类工具，输入来源支持 `capture_id`，描述工具同时支持 `inline_image`。
- 新增图像预处理、尺寸限制、超时、并发控制与审计字段，确保视觉链路可追踪、可限流、可关闭。
- 明确当 vision 未启用、配置缺失或 provider 不可用时，相关工具返回 `capability_unavailable`，而不是影响其他 MCP 能力。
- 明确本 change 只覆盖 `disabled` 与 `assist` 两种运行模式，不实现危险动作前后的 `guard` 检查；该模式留给后续 hardening change 承接。
- 依赖链位置：前置为 `add-batch-wait-diff`；这是当前 MVP/change 链的最后一段，后续若继续推进则进入 hardening 与 beta-ready 方向。

## Capabilities

### New Capabilities

- `ollama-vision-assist`: 定义本地 Ollama 视觉辅助、预处理、可用性降级与结果结构。

### Modified Capabilities

无。

## Impact

- 引入 Ollama 本地 HTTP provider、视觉配置项与并发控制。
- 影响 capture artifact 的复用方式、图像预处理和视觉审计字段。
- 为上层 agent 提供本地 describe / locate 能力，但不改变已有 observe/input/batch 工具契约。
