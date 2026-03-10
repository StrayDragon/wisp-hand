## MODIFIED Requirements

### Requirement: 服务必须返回完整的 Hyprland 拓扑快照

Wisp Hand 服务 MUST 通过 `hand.desktop.get_topology` 返回当前 Hyprland 会话的 monitors、workspaces、active workspace、active window 与 windows 列表, 并保持字段结构稳定.

此外, 返回结果 MUST 补齐坐标映射上下文, 以支持 mixed-scale 多显示器下的稳定 capture/input/vision:

- `coordinate_backend`: 当前坐标后端选择结果(至少包含 `backend`, `confidence`, `topology_fingerprint`, `cached`)
- `desktop_layout_bounds`: 以 layout/logical px 表示的桌面边界
- `monitors[*].layout_bounds`: 以 layout/logical px 表示的 monitor 边界
- `monitors[*].physical_size`: 以 physical px 表示的 monitor 像素尺寸
- `monitors[*].scale`
- `monitors[*].pixel_ratio`: image px 与 layout px 的比例(允许 x/y 分离)

#### Scenario: Hyprland 环境下返回拓扑快照

- **WHEN** 客户端在受支持的 Hyprland 环境中调用 `hand.desktop.get_topology`
- **THEN** 服务返回 monitors、workspaces、active_workspace、active_window 与 windows 字段, 且包含 `coordinate_backend` 与 `desktop_layout_bounds`, 并为每个 monitor 提供 `layout_bounds/physical_size/scale/pixel_ratio`

#### Scenario: 非 Hyprland 环境被明确拒绝

- **WHEN** 客户端在非 Hyprland 环境中调用 `hand.desktop.get_topology`
- **THEN** 服务 MUST 返回 `unsupported_environment`, 而不是伪造空拓扑结果

