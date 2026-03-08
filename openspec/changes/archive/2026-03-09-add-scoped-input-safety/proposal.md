## Why

只读 observe 链路打通后，系统已经能稳定看到桌面与作用域，但仍然不能产生任何副作用。MVP 的核心价值不是“看见”，而是在可控边界内稳定点击、输入和滚动，因此下一步必须把输入执行和安全控制一起落地。

这个 change 专门负责把 scope 内输入、arming、dry-run、限速与 emergency stop 收拢到同一套行为契约里，避免输入能力先落地、再回头补安全控制。

## What Changes

- 新增 scope 内 pointer 与 keyboard 输入能力，覆盖移动、点击、拖拽、滚动、文本输入、按键与组合键。
- 新增输入前的 scope 边界检查与桌面坐标映射，确保所有副作用动作都以 session scope 为唯一参照。
- 新增 `armed` 检查、`dry_run`、最大动作频率限制、危险动作拒绝与 emergency stop 锁存机制。
- 统一所有输入行为的审计记录，确保成功、失败与被拒绝动作都可追踪。
- 明确本 change 不实现 batch orchestration、wait、capture diff 或 vision 推理。
- 依赖链位置：前置为 `add-hyprland-observe-capture`；完成后直接承接 `add-batch-wait-diff`，并为 `add-ollama-vision-assist` 提供可与视觉结果配合的稳定输入面。

## Capabilities

### New Capabilities

- `scoped-input-control`: 定义 scope 内 pointer / keyboard tool surface 与坐标映射规则。
- `input-safety-guardrails`: 定义 arming、dry-run、rate limit、policy deny 与 emergency stop 契约。

### Modified Capabilities

无。

## Impact

- 影响所有会产生副作用的 MCP tools。
- 影响 session 的安全状态流转、scope 校验、动作调度与审计字段。
- 为后续 batch、vision-assisted locate-to-click 等能力提供稳定执行面。
