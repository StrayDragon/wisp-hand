## MODIFIED Requirements

### Requirement: 服务必须支持目标定位能力

Wisp Hand 服务 MUST 通过 `wisp_hand.vision.locate` 基于 `capture_id` 与文本目标返回候选区域列表。

为了保证 token-efficient，`wisp_hand.vision.locate` MUST 支持以下参数：

- `limit`：限制返回候选数量。默认 MUST 为 3。
- `space`：控制返回坐标空间，取值 MUST 为 `scope`、`image` 或 `both`。默认 MUST 为 `scope`。

当 `space=scope` 时，每个候选 MUST 至少包含 `x`、`y`、`width`、`height`、`confidence` 与 `reason`（scope 坐标）。

当 `space=image` 时，返回的候选 MUST 为 image 坐标。

当 `space=both` 时，服务 MUST 同时返回 scope 与 image 坐标的候选集合。

#### Scenario: locate 默认返回少量 scope 候选

- **WHEN** 客户端调用 `wisp_hand.vision.locate` 且未提供 `limit` 与 `space`
- **THEN** 服务返回最多 3 个候选，且默认只返回 scope 坐标候选

#### Scenario: locate 显式请求 both 返回两套坐标

- **WHEN** 客户端调用 `wisp_hand.vision.locate(space=both)`
- **THEN** 服务同时返回 scope 与 image 坐标候选集合

#### Scenario: 非法 space 被拒绝

- **WHEN** 客户端调用 `wisp_hand.vision.locate` 且提供不支持的 `space` 值
- **THEN** 服务 MUST 返回 `invalid_parameters`

