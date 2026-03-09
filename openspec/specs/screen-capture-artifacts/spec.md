# screen-capture-artifacts Specification

## Purpose
定义多目标截图、artifact store 与 capture 元数据契约，为输入、diff 与视觉能力提供可复用图像来源。
## Requirements
### Requirement: 服务必须支持多目标截图

Wisp Hand 服务 MUST 通过 `hand.capture.screen` 支持 `desktop`、`monitor`、`window`、`region` 与 `scope` 五类截图目标，并为每次截图生成唯一的 `capture_id`。

#### Scenario: 基于 scope 生成截图

- **WHEN** 客户端以 `target=scope` 调用 `hand.capture.screen`
- **THEN** 服务返回对应 scope 的截图结果，而不是回退为全桌面截图

#### Scenario: 基于 window 生成截图

- **WHEN** 客户端以 `target=window` 调用 `hand.capture.screen` 且目标窗口存在
- **THEN** 服务返回目标窗口边界内的截图结果

#### Scenario: 缺少截图依赖时明确失败

- **WHEN** 客户端调用 `hand.capture.screen` 且截图后端依赖缺失
- **THEN** 服务 MUST 返回 `dependency_missing`

### Requirement: 截图结果必须进入 artifact store 并附带标准元数据

每次截图 MUST 写入 capture artifact store，并返回至少包含 `capture_id`、`scope`、`width`、`height`、`mime_type`、`path` 或 `inline_base64`、`created_at` 的标准元数据。

#### Scenario: 默认返回文件引用

- **WHEN** 客户端以 `inline=false` 调用 `hand.capture.screen`
- **THEN** 服务返回 `capture_id` 与可访问的 artifact `path`

#### Scenario: 显式请求内联图像

- **WHEN** 客户端以 `inline=true` 调用 `hand.capture.screen`
- **THEN** 服务返回 `inline_base64`，同时仍保留可审计的 `capture_id` 与截图元数据

### Requirement: 截图元数据必须保留坐标映射上下文

capture 元数据 MUST 保留目标类型、原始几何边界与 downscale 上下文，以便后续 input、diff 与 vision 链路把图像坐标映射回桌面或 scope 坐标。

#### Scenario: Downscale 截图仍可回溯原始边界

- **WHEN** 客户端请求 downscale 后的截图
- **THEN** 返回的 capture 元数据仍包含足以回溯到原始 scope 或目标边界的上下文字段
