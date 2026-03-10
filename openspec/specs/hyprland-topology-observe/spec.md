# hyprland-topology-observe Specification

## Purpose
定义 Hyprland 拓扑与光标查询的稳定只读能力，为后续 scope、capture、input 与 batch 链路提供共享观察上下文。
## Requirements
### Requirement: 服务必须返回完整的 Hyprland 拓扑快照

Wisp Hand 服务 MUST 通过 `wisp_hand.desktop.get_topology` 返回 Hyprland 拓扑, 并支持通过参数 `detail` 控制返回详细度:

- `detail=summary` (默认): 返回拓扑摘要, 用于高频 agent 观察. 返回 MUST 包含 `monitors`, `workspaces`, `active_workspace`, `active_window`, `coordinate_backend`, `desktop_layout_bounds`, 并且 MUST NOT 返回 `windows` 列表.
- `detail=full`: 返回包含窗口列表的拓扑结果. 返回 MUST 包含 `windows` 列表, 并且该列表元素 MUST 至少包含可用于 selector 与几何计算的稳定字段集合(例如 `address`, `class`, `title`, `workspace`, `monitor`, `at`, `size`).
- `detail=raw`: 用于诊断/排障. 返回 MUST 在 `detail=full` 的基础上额外包含 `raw` 字段, 其中包含 Hyprland 原始 JSON payload(至少覆盖 `monitors/workspaces/active_workspace/active_window/windows`).

在 `detail=summary` 与 `detail=full` 模式下, 返回结果 MUST 保留 mixed-scale 多显示器下可复用的坐标映射上下文, 至少包括:

- `coordinate_backend`: 至少包含 `backend`, `confidence`, `topology_fingerprint`, `cached`
- `desktop_layout_bounds`: 以 layout/logical px 表示的桌面边界
- `monitors[*].layout_bounds`: 以 layout/logical px 表示的 monitor 边界
- `monitors[*].physical_size`: 以 physical px 表示的 monitor 像素尺寸
- `monitors[*].scale`
- `monitors[*].pixel_ratio`: image px 与 layout px 的比例(允许 x/y 分离)

此外, 为了保证默认返回 token-efficient, 在 `detail=summary` 与 `detail=full` 模式下:

- `monitors[*]` MUST NOT 包含明显大体积且不用于几何/映射的诊断字段(例如 `availableModes`).
- 若需要 Hyprland 诊断字段, 客户端 MUST 通过 `detail=raw` 显式请求.

#### Scenario: 默认返回拓扑摘要

- **WHEN** 客户端在受支持的 Hyprland 环境中调用 `wisp_hand.desktop.get_topology` 且不提供 `detail`
- **THEN** 服务 MUST 返回 `detail=summary` 的拓扑摘要, 包含 `monitors/workspaces/active_workspace/active_window/coordinate_backend/desktop_layout_bounds`, 并且 MUST NOT 返回 `windows` 字段

#### Scenario: 显式请求 full 返回包含窗口列表

- **WHEN** 客户端在受支持的 Hyprland 环境中调用 `wisp_hand.desktop.get_topology(detail=full)`
- **THEN** 服务 MUST 返回包含 `windows` 列表的拓扑结果, 并且 `windows[*]` MUST 至少包含 `address/class/title/workspace/monitor/at/size`

#### Scenario: 显式请求 raw 返回可诊断的原始 payload

- **WHEN** 客户端在受支持的 Hyprland 环境中调用 `wisp_hand.desktop.get_topology(detail=raw)`
- **THEN** 服务 MUST 在返回中包含 `raw` 字段, 且 `raw` MUST 至少包含 Hyprland 原始 `monitors/workspaces/active_workspace/active_window/windows` JSON payload

#### Scenario: 非 Hyprland 环境被明确拒绝

- **WHEN** 客户端在非 Hyprland 环境中调用 `wisp_hand.desktop.get_topology`
- **THEN** 服务 MUST 返回 `unsupported_environment`, 而不是伪造空拓扑结果

#### Scenario: 非法 detail 被拒绝

- **WHEN** 客户端调用 `wisp_hand.desktop.get_topology` 且提供不支持的 `detail` 值
- **THEN** 服务 MUST 返回 `invalid_parameters`

### Requirement: 服务必须返回光标的绝对与作用域相对坐标

Wisp Hand 服务 MUST 通过 `wisp_hand.cursor.get_position` 返回桌面绝对坐标，并在提供 `session_id` 时返回与 session scope 对齐的相对坐标。

#### Scenario: 有效 session 返回相对坐标

- **WHEN** 客户端使用有效 `session_id` 调用 `wisp_hand.cursor.get_position`
- **THEN** 服务返回 `x`、`y`、`scope_x` 与 `scope_y`

#### Scenario: 无效 session 被拒绝

- **WHEN** 客户端使用不存在或已过期的 `session_id` 调用 `wisp_hand.cursor.get_position`
- **THEN** 服务 MUST 返回 `session_not_found` 或 `session_expired`

