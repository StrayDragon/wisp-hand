## ADDED Requirements

### Requirement: 未 armed 的 session 不得产生副作用

所有 pointer 与 keyboard 输入 MUST 仅在 `armed=true` 时允许执行；未 armed 的 session 只能调用 observe 类工具，不能产生任何副作用。

#### Scenario: 未 armed session 调用输入工具被拒绝

- **WHEN** 客户端使用 `armed=false` 的 session 调用任意输入工具
- **THEN** 服务 MUST 返回 `session_not_armed`

### Requirement: Dry-run 必须保留验证语义但不产生副作用

当 session 处于 `dry_run=true` 时，输入链路 MUST 完整走过参数校验、scope 检查、策略检查与审计记录，但不得向桌面实际发送输入事件。

#### Scenario: Dry-run 输入只记录不执行

- **WHEN** 客户端使用 `dry_run=true` 的 session 调用任意输入工具
- **THEN** 服务返回可预期的模拟结果并记录审计，但桌面状态不发生改变

### Requirement: 输入链路必须受策略护栏控制

输入链路 MUST 支持 emergency stop 锁存、最大动作频率限制与危险动作拒绝，并在触发时返回结构化策略错误。

#### Scenario: Emergency stop 触发后拒绝新动作

- **WHEN** emergency stop 已被触发后客户端继续调用任意输入工具
- **THEN** 服务 MUST 返回 `policy_denied` 并拒绝新的输入 dispatch

#### Scenario: 超出动作频率限制时拒绝输入

- **WHEN** 客户端在单位时间内连续发送超过配置阈值的输入动作
- **THEN** 服务 MUST 返回 `policy_denied` 并指出触发了频率限制

#### Scenario: 危险快捷键被策略拒绝

- **WHEN** 客户端调用 `hand.keyboard.press` 且请求的按键组合被策略列为危险动作
- **THEN** 服务 MUST 返回 `policy_denied`
