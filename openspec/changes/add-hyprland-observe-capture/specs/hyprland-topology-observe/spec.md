## ADDED Requirements

### Requirement: 服务必须返回完整的 Hyprland 拓扑快照

Wisp Hand 服务 MUST 通过 `hand.desktop.get_topology` 返回当前 Hyprland 会话的 monitors、workspaces、active workspace、active window 与 windows 列表，并保持字段结构稳定。

#### Scenario: Hyprland 环境下返回拓扑快照

- **WHEN** 客户端在受支持的 Hyprland 环境中调用 `hand.desktop.get_topology`
- **THEN** 服务返回 monitors、workspaces、active_workspace、active_window 与 windows 字段，且几何信息可被后续 scope 与 capture 复用

#### Scenario: 非 Hyprland 环境被明确拒绝

- **WHEN** 客户端在非 Hyprland 环境中调用 `hand.desktop.get_topology`
- **THEN** 服务 MUST 返回 `unsupported_environment`，而不是伪造空拓扑结果

### Requirement: 服务必须返回光标的绝对与作用域相对坐标

Wisp Hand 服务 MUST 通过 `hand.cursor.get_position` 返回桌面绝对坐标，并在提供 `session_id` 时返回与 session scope 对齐的相对坐标。

#### Scenario: 有效 session 返回相对坐标

- **WHEN** 客户端使用有效 `session_id` 调用 `hand.cursor.get_position`
- **THEN** 服务返回 `x`、`y`、`scope_x` 与 `scope_y`

#### Scenario: 无效 session 被拒绝

- **WHEN** 客户端使用不存在或已过期的 `session_id` 调用 `hand.cursor.get_position`
- **THEN** 服务 MUST 返回 `session_not_found` 或 `session_expired`
