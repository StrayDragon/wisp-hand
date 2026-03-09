# session-runtime Specification

## Purpose
定义 session 生命周期、scope envelope 与基础能力自检契约，作为所有后续副作用与观察工具的公共 runtime 基座。
## Requirements
### Requirement: 基础能力必须可自检

Wisp Hand 服务 MUST 暴露 `hand.capabilities` 工具，用于报告当前环境的能力状态、关键依赖以及缺失项，而不是把环境探测分散到后续功能里。

#### Scenario: 依赖完整时返回能力矩阵

- **WHEN** 客户端调用 `hand.capabilities` 且运行环境满足基础依赖
- **THEN** 服务返回 `hyprland_detected`、`capture_available`、`input_available`、`vision_available`、`required_binaries`、`missing_binaries` 等结构化字段

#### Scenario: 缺少依赖时仍能完成自检

- **WHEN** 客户端调用 `hand.capabilities` 且 `hyprctl` 或其他关键依赖缺失
- **THEN** 服务 MUST 返回缺失项列表与能力降级结果，而不是崩溃、挂起或输出非结构化报错

### Requirement: 服务必须支持显式 session 生命周期

Wisp Hand 服务 MUST 通过 `hand.session.open` 与 `hand.session.close` 管理显式 session，并为每个 session 维护唯一 `session_id`、默认 scope、`armed`、`dry_run` 与 `expires_at` 状态。

#### Scenario: 打开 session 返回完整状态

- **WHEN** 客户端调用 `hand.session.open` 并提供 scope、arming、dry-run 与 TTL 参数
- **THEN** 服务返回新的 `session_id`、标准化后的 `scope`、`armed`、`dry_run` 与 `expires_at`

#### Scenario: 关闭后的 session 不再可用

- **WHEN** 客户端关闭某个 session 后继续使用该 `session_id`
- **THEN** 服务 MUST 返回结构化的 `session_not_found` 错误

#### Scenario: 过期 session 被拒绝

- **WHEN** 某个 session 的 TTL 到期后又被后续工具引用
- **THEN** 服务 MUST 返回结构化的 `session_expired` 错误并阻止继续执行

### Requirement: Session 必须绑定统一的 scope envelope

每个 session MUST 绑定一个标准化的 scope envelope，至少包含 `type`、`target`、坐标空间元数据与运行约束，以便后续 observe、input、batch、vision 工具共享同一作用域上下文。

#### Scenario: 创建 region scope 时写入标准化 envelope

- **WHEN** 客户端以矩形区域创建 session
- **THEN** 服务返回的 session 状态中包含标准化后的 region scope，而不是原始未校验输入

#### Scenario: 下游工具读取同一份 scope 元数据

- **WHEN** 后续工具通过 `session_id` 读取 session
- **THEN** 它们 MUST 获取同一份标准化 scope envelope，而不是各自重新解释 scope 参数
