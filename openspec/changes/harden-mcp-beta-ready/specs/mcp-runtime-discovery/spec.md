## ADDED Requirements

### Requirement: 外部接入方必须可以在连接前执行 runtime preflight

Wisp Hand MUST 提供 `wisp-hand-mcp doctor --json` 作为连接前预检入口，并返回机器可读的 runtime discovery 报告。该报告至少必须包含 `version`、`config_path`、`transport`、依赖检查结果、关键路径可写性、启用能力摘要、总体 `status` 与阻塞问题列表。

#### Scenario: 有效环境返回 ready 预检报告

- **WHEN** 操作方在有效配置、依赖完整且关键写路径可用的环境下执行 `wisp-hand-mcp doctor --json`
- **THEN** 命令 MUST 返回结构化 JSON 报告，并把总体 `status` 标记为 `ready`

#### Scenario: 阻塞问题会阻止通过预检

- **WHEN** 操作方执行 `wisp-hand-mcp doctor --json` 时存在配置非法、关键依赖缺失或关键路径不可写
- **THEN** 命令 MUST 以非零状态退出，并返回包含阻塞项详情的结构化报告，而不是直接挂起或只输出自由文本

### Requirement: 已连接客户端必须可以发现 live runtime 元数据

`wisp_hand.capabilities` MUST 在现有能力矩阵基础上，返回当前运行实例的元数据，至少包含 `version`、`runtime_instance_id`、`started_at`、`transport`、`implemented_tools`、能力可用性、依赖检查摘要与 retention 摘要。

#### Scenario: 连接后可读取当前实例元数据

- **WHEN** 客户端连接到一个已启动的 Wisp Hand 实例并调用 `wisp_hand.capabilities`
- **THEN** 服务 MUST 返回当前实例的 `runtime_instance_id`、`started_at`、`transport` 与完整 discovery 摘要

#### Scenario: 重启后的实例标识可被发现

- **WHEN** 客户端在服务重启前后分别调用 `wisp_hand.capabilities`
- **THEN** 两次结果中的 `runtime_instance_id` MUST 不同，以便客户端识别 runtime 已切换到新实例

### Requirement: discovery 输出必须显式描述 transport 契约

连接前和连接后的 discovery 输出 MUST 以稳定字段显式描述当前 transport；当 transport 为网络模式时，还必须暴露外部接入所需的绑定信息。

#### Scenario: stdio 模式返回无绑定的 transport 描述

- **WHEN** runtime 配置使用 `stdio`
- **THEN** discovery 输出 MUST 明确标记 `transport=stdio`，且不要求客户端再推断网络地址

#### Scenario: 网络模式返回绑定信息

- **WHEN** runtime 配置使用 `sse` 或 `streamable-http`
- **THEN** discovery 输出 MUST 返回与当前实例一致的 `host`、`port` 等绑定信息，供外部客户端直接接入
