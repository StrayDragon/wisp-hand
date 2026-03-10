## ADDED Requirements

### Requirement: 服务必须支持查询当前 active window 的最小只读能力

Wisp Hand 服务 MUST 通过 `wisp_hand.desktop.get_active_window` 返回当前 active window 的最小、稳定、可用于 selector 与几何计算的字段集合，至少包含：

- `address`
- `class`
- `title`
- `workspace`（至少包含 `id` 与 `name`）
- `monitor`
- `at`
- `size`

#### Scenario: 返回 active window 最小字段集合

- **WHEN** 客户端在受支持的 Hyprland 环境中调用 `wisp_hand.desktop.get_active_window`
- **THEN** 服务返回包含 `address/class/title/workspace/monitor/at/size` 的结构化结果，且不包含窗口全量列表

### Requirement: 服务必须支持查询 monitors 的最小几何与坐标映射上下文

Wisp Hand 服务 MUST 通过 `wisp_hand.desktop.get_monitors` 返回当前 monitors 的最小几何与 mixed-scale 坐标映射上下文，至少包含：

- `name`（或 `id`）
- `layout_bounds`
- `physical_size`
- `scale`
- `pixel_ratio`

并且 MUST NOT 返回明显大体积且不用于几何/映射的诊断字段（例如 `availableModes`）。

#### Scenario: 返回 monitors 的最小映射上下文

- **WHEN** 客户端在受支持的 Hyprland 环境中调用 `wisp_hand.desktop.get_monitors`
- **THEN** 服务返回每个 monitor 的 `layout_bounds/physical_size/scale/pixel_ratio`，且不包含 `availableModes`

### Requirement: 服务必须支持按需枚举窗口列表（带 limit）

Wisp Hand 服务 MUST 通过 `wisp_hand.desktop.list_windows` 支持按需枚举窗口列表，并支持参数 `limit` 以限制返回条目数。

返回的窗口对象 MUST 至少包含可用于 selector 与几何计算的最小字段集合：

- `address`
- `class`
- `title`
- `workspace`
- `monitor`
- `at`
- `size`

#### Scenario: list_windows 返回受 limit 限制的窗口列表

- **WHEN** 客户端在受支持的 Hyprland 环境中调用 `wisp_hand.desktop.list_windows(limit=10)`
- **THEN** 服务返回最多 10 个窗口对象，且每个窗口对象包含 `address/class/title/workspace/monitor/at/size`

#### Scenario: 非法 limit 被拒绝

- **WHEN** 客户端调用 `wisp_hand.desktop.list_windows` 且提供 `limit<=0`
- **THEN** 服务 MUST 返回 `invalid_parameters`

