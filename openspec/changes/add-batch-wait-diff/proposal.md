## Why

observe 和 scoped input 打通后，agent 已经能读取界面并执行单步动作，但每一步都要单独往返会放大坐标漂移、状态抖动和 tool-call 成本。要让桌面闭环更稳定，必须补上批处理、基础等待和截图差异能力。

这个 change 的目标不是新增更危险的底层动作，而是把前面已经定义好的 observe 与 input 能力组合起来，形成更可靠的执行闭环。

## What Changes

- 新增 `hand.batch.run`，在同一 session 与 scope 内顺序执行多步动作，并支持 fail-fast 与逐步结果返回。
- 新增 `hand.wait` 的固定时长等待能力，供 batch 和上层 agent 在动作之间显式插入稳定化间隔。
- 新增 `hand.capture.diff`，用于基于两个 `capture_id` 做像素级差异比较并返回变更比例与确定性摘要。
- 明确 batch 只复用已有 observe/input/safety 链路，不允许绕过已有 session、scope、arming、policy 与 audit 约束。
- 明确本 change 不实现 window 出现等待、active window 变化等待或 VLM 级截图对比总结，这些增强能力留到后续版本。
- 依赖链位置：前置为 `add-scoped-input-safety`；完成后直接承接 `add-ollama-vision-assist`，同时为后续更复杂的 agent 闭环提供最小可靠编排层。

## Capabilities

### New Capabilities

- `action-batch-runner`: 定义在单个 session / scope 中编排多步动作的批处理能力。
- `state-wait-and-diff`: 定义固定时长等待与 capture diff 的基础观察闭环。

### Modified Capabilities

无。

## Impact

- 影响上层 agent 的调用粒度与错误恢复方式。
- 影响 observe/input 的审计关联 ID、步骤结果结构与截图复用方式。
- 为后续 vision-assisted comparison、复杂策略钩子与 debug trace 提供基础编排入口。
