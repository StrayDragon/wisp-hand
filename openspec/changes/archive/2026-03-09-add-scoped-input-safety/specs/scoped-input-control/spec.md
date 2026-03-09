## ADDED Requirements

### Requirement: Pointer 输入必须在 session scope 内执行

Wisp Hand 服务 MUST 通过 `hand.pointer.move`、`hand.pointer.click`、`hand.pointer.drag` 与 `hand.pointer.scroll` 在 session scope 内执行 pointer 动作，并在 dispatch 前把 scope-relative 坐标转换为桌面绝对坐标。

#### Scenario: Scope 内点击成功执行

- **WHEN** 客户端使用已 armed 的有效 session 调用 `hand.pointer.click` 且目标坐标位于 scope 内
- **THEN** 服务执行点击并返回成功结果与相关审计上下文

#### Scenario: 越界 pointer 动作被拒绝

- **WHEN** 客户端调用任意 pointer 工具且目标坐标超出 session scope
- **THEN** 服务 MUST 返回 `scope_violation`

### Requirement: Keyboard 输入必须通过统一 tool surface 暴露

Wisp Hand 服务 MUST 通过 `hand.keyboard.type` 与 `hand.keyboard.press` 暴露文本输入、单键与组合键能力，并让所有 keyboard 动作绑定到同一 session 安全状态与审计链路。

#### Scenario: 文本输入成功执行

- **WHEN** 客户端使用已 armed 的有效 session 调用 `hand.keyboard.type`
- **THEN** 服务执行文本输入并返回成功结果

#### Scenario: 组合键成功执行

- **WHEN** 客户端使用已 armed 的有效 session 调用 `hand.keyboard.press` 并提供组合键序列
- **THEN** 服务执行组合键并记录按键参数与执行结果

### Requirement: 所有输入动作都必须走统一的 session 校验路径

任意 pointer 或 keyboard 工具 MUST 先解析 `session_id`、读取标准化 scope envelope 与当前安全状态，再决定是否允许执行。

#### Scenario: 缺失 session 时拒绝输入

- **WHEN** 客户端对不存在或已过期的 session 调用任意输入工具
- **THEN** 服务 MUST 返回 `session_not_found` 或 `session_expired`
