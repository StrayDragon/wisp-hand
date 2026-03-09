## Context

前两个 change 让系统具备了观察能力和单步输入能力，但上层 agent 仍然只能以“一次一个 tool call”的方式驱动桌面。这样既增加往返开销，也让“动作之后等一下再截图”这种稳定化流程散落在客户端，难以统一审计和重放。

本 change 把组合能力收敛到 runtime 内部，但坚持不新增任何绕过前序安全校验的捷径。

## Goals / Non-Goals

**Goals:**

- 提供顺序批处理与逐步结果回传。
- 提供固定时长等待与像素级 capture diff。
- 保证 batch 内每一步都复用已有 observe/input/safety 链路。
- 为上层 agent 减少多轮往返与状态抖动。

**Non-Goals:**

- 不实现 window 出现等待、活动窗口变化等待或截图变化阈值等待。
- 不引入新的底层输入原语或绕过策略层的快速路径。
- 不实现 VLM 级 diff 总结或视觉推理。

## Decisions

### 1. Batch 是 orchestrator，不是新的执行后端

`hand.batch.run` 不直接调用底层适配器，而是复用现有 observe/input 工具背后的同一执行管线。这样 batch 内的每一步都会自动继承 session 校验、scope 边界检查、arming、policy deny 与 audit。

### 2. Batch 结果必须按步骤可追踪

返回结果中按步骤保存：

- step index
- step type
- status
- output 或 error
- 相关 capture 引用

这样失败时可以精确定位步骤，而不是只得到一个整批失败结论。

### 3. Wait 只做固定时长，不提前做隐式状态等待

当前 change 只交付确定性的 `duration_ms` 等待。窗口出现、active window 变化、截图变化阈值等待都依赖更多观察语义，留给后续版本单独扩展，避免在本 change 内掺入模糊轮询逻辑。

### 4. Diff 先做确定性的像素比较

`hand.capture.diff` 当前只负责基于已有 capture artifact 做像素差异计算和确定性摘要，不接入视觉模型。这样它既能服务基础闭环，也不会和后续 vision change 的职责重叠。

## Risks / Trade-offs

- Batch 把多个步骤打包后，单次调用失败成本更高 -> 通过逐步结果与 fail-fast 选项降低排查难度。
- Wait 和 diff 放到 runtime 内会增加状态管理复杂度 -> 但它能换来统一审计和更稳定的 agent 闭环。
- 只提供固定时长等待会限制部分高级场景 -> 这是有意的范围收缩，用来换取明确、可验证的 MVP 行为。
