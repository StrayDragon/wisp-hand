## MODIFIED Requirements

### Requirement: 服务必须支持目标定位能力

Wisp Hand 服务 MUST 通过 `wisp_hand.vision.locate` 基于 `capture_id` 与文本目标返回候选区域列表.

为避免缩放/多显示器下的坐标歧义, `wisp_hand.vision.locate` 的输出 MUST 显式区分坐标系:

- `candidates_scope`: 候选区域(坐标系为 scope/layout px, 可直接用于 `wisp_hand.pointer.*` 的 scope 坐标)
- `candidates_image`: 候选区域(坐标系为 image px, 用于调试与高级 fallback)

每个候选 MUST 至少包含 `x`、`y`、`width`、`height`、`confidence` 与 `reason`.

#### Scenario: 定位返回候选区域

- **WHEN** 客户端对有效 `capture_id` 调用 `wisp_hand.vision.locate` 并提供文本目标
- **THEN** 服务返回一个或多个候选区域, 且同时包含 `candidates_scope` 与 `candidates_image`, 并保证 `candidates_scope` 与 capture 的 `source_bounds`(layout px)一致
