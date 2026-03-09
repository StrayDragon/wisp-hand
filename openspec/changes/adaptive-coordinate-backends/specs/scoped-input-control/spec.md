## MODIFIED Requirements

### Requirement: Pointer 输入必须在 session scope 内执行

Wisp Hand 服务 MUST 通过 `hand.pointer.move`、`hand.pointer.click`、`hand.pointer.drag` 与 `hand.pointer.scroll` 在 session scope 内执行 pointer 动作, 并在 dispatch 前把 scope-relative 坐标转换为桌面绝对坐标.

坐标契约 MUST 满足:

- 工具入参 `x/y` MUST 解释为 scope 内的 **layout/logical px**
- scope-relative -> desktop-absolute 的映射 MUST 基于坐标后端提供的 `layout_bounds`, 而不是 physical px
- 当输入后端使用 absolute motion/extent 归一化(例如 virtual pointer)时, extent MUST 使用 `desktop_layout_bounds`

#### Scenario: Scope 内点击成功执行

- **WHEN** 客户端使用已 armed 的有效 session 调用 `hand.pointer.click` 且目标坐标位于 scope 内
- **THEN** 服务执行点击并返回成功结果与相关审计上下文, 且该点击在缩放显示器下仍与 scope/layout 坐标一致

#### Scenario: 越界 pointer 动作被拒绝

- **WHEN** 客户端调用任意 pointer 工具且目标坐标超出 session scope
- **THEN** 服务 MUST 返回 `scope_violation`

